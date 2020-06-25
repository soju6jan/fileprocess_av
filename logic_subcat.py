# -*- coding: utf-8 -*-
#########################################################
# python
import os
import sys
import traceback
import time
import threading
import shutil
import re
from datetime import datetime, timedelta
import urllib

# third-party
import requests
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest
from plexapi.library import ShowSection

try:
    from bs4 import BeautifulSoup
except:
    os.system('pip install bs4')
    from bs4 import BeautifulSoup

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util
import framework.common.fileprocess as FileProcess
from plex.model import ModelSetting as PlexModelSetting

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem, SubModelItem
#########################################################

class LogicSubcat(object):
    @staticmethod
    def handler_function(func_type, param):
        logger.debug('%s SUBCAT HANDLER(%s)', __name__, func_type)
        if app.config['config']['use_celery']:
            result = LogicSubcat.task.apply_async((func_type,param,))
            result.get()
        else:
            LogicSubcat.task(func_type,param)

    @staticmethod
    @celery.task
    def task(func_type, param):
        try:
            logger.debug('%s SUBCAT HANDLER TASK(%s)', __name__, func_type)
            if func_type == 'one_execute':
                return LogicSubcat.one_execute()
            elif func_type == 'manual_execute':
                return LogicSubcat.manual_execute(param)
            elif func_type == 'force_execute':
                return LogicSubcat.force_execute()
            elif func_type == 'proc_single':
                return LogicSubcat.process_single_by_id(param, force=True)
            elif func_type == 'proc_expire':
                return LogicSubcat.process_expire_by_id(param)
            elif func_type == 'proc_remove':
                return LogicSubcat.process_remove_by_id(param)
            elif func_type == 'recent':
                return LogicSubcat.process_recent()
            return True

        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def get_response(url):
        for i in range(1, 3 + 1):
            try:
                r = requests.get(url)
                if r.status_code == 200 and len(r.text) > 1024: break
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return None

        if i == 3:
            logger.error('failed to get response(url:%s)', url)
            return None
    
        return r

    @staticmethod
    def down_sub(url, path):
        keyword, dname, name, ext = LogicSubcat.parse_fname(path)
        entity = SubModelItem.get_entity(keyword)
        entity.sub_url = url
    
        r = LogicSubcat.get_response(url)
        if r is None:
            logger.error('failed to download subfile(key:%s, url:%s)', keyword, url)
            entity.sub_status = 99
            entity.save()
            return False
        
        fname = name + ModelSetting.get('subcat_subext')
        tmp_f = os.path.join(ModelSetting.get('subcat_tmp_path'), fname)
        dst_f = os.path.join(dname, fname)
    
        logger.info('download sub to: %s', tmp_f)
        
        f = open(tmp_f, mode='wb')
        size = f.write(r.text.encode('utf-8'))
        f.close()

        logger.info('move     sub to: %s' % dst_f)
        shutil.move(tmp_f, dst_f)
        LogicSubcat.metadata_refresh(filepath=path)

        entity.sub_status = 3
        entity.sub_name = fname
        entity.save()

        return True

    @staticmethod
    def get_suburl(key):
        SURL = '/index.php?search={keyword}'
        url = ModelSetting.get('subcat_url') + SURL.format(keyword=key)
        logger.debug('try to search sublist (%s), url(%s)', key, url)

        entity = SubModelItem.get_entity(key)
        entity.search_cnt = entity.search_cnt + 1
        entity.last_search= datetime.now()
        entity.sub_status = 0

        r = LogicSubcat.get_response(url)
        if r is None:
            print 'failed to get sublist(key:%s, url:%s)' %(key, url)
            entity.sub_status = 99
            entity.save()
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        tab  = soup.find('table', {'class':'table table_index table-hover'})
        if tab.find('td') is None: 
            print 'sub file does not exist(key:%s)' % key
            entity.sub_status = 0
            entity.save()
            return None

        trs = tab.find_all('tr')
        LANGS = ModelSetting.get_list('subcat_langs')
        for lang in LANGS:
            found= False
            text = 'from {lang}'.format(lang=lang)
            regx = re.compile(text, re.I)
            logger.debug('search for lang(%s)' % lang)
            for tr in trs:
                if tr.find('td') is None: continue
                rx = regx.search(tr.td.text)
                if rx is None: 
                    logger.info('not found subfile for target lang(key:%s, lang:%s)', key, lang)
                    continue

                logger.info('found subfile for target lang(key:%s, lang:%s)', key, lang)
                found = True
                break

            if found is True:
                uri = tr.td.a['href']
                sublisturl = ModelSetting.get('subcat_url') + '/' + uri
                enc_uri = uri[uri.rfind('/')+1:uri.rfind('.')]
                logger.debug('sublisturl: %s', sublisturl)
                r = LogicSubcat.get_response(sublisturl)
                if r is None:
                    logger.info('failed to get sublist url(key:%s, url:%s)', key, sublisturl)
                    entity.sub_status = 99
                    entity.save()
                    return None

                soup = BeautifulSoup(r.text, "html.parser")
                tdsub = soup.find('td', text='Korean') # TODO: 여러언어 처리
                
                if tdsub.parent.find('button') is not None:
                    logger.info('failed to get subfile url')
                    entity.sub_status = 99
                    entity.save()
                    return None

                tmpurl = tdsub.find_next('td').a['href']
                suburl = ModelSetting.get('subcat_url') + tmpurl[:tmpurl.rfind('/')+1] + enc_uri + tmpurl[tmpurl.rfind('-'):]
                entity.sub_status = 2
                entity.save()
                return suburl
        return None


    @staticmethod
    def parse_fname(path):
        fpath, ext = os.path.splitext(path)
    
        name  = fpath[fpath.rfind('/')+1:]
        fpath = fpath[:fpath.rfind('/')+1]
    
        if name.find(" [") > 0: key = name[:name.find('[')]
        else: key = name
    
        # XXXX-123cdx 처리 -> XXXX-123
        r = re.compile("cd[0-9]", re.I).search(key)
        if r is not None: key = key[:r.start()]
    
        return key.strip(), fpath, name, ext

    @staticmethod
    def process_single_by_id(data_id, force=False):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entity = SubModelItem.get_entity_by_id(data_id)
            if entity is None:
                logger.error('failed to find SubModelItem(id:%d)', id)
                return False
            file_path = entity.media_path + entity.media_name
            logger.debug('process_single_by_id started(path:%s)', file_path)

            # for test
            libkey = LogicSubcat.get_library_key_using_bundle(file_path, -1)
            if os.path.isfile(file_path) is False:
                logger.warning('target file does not exist(path:%s)', path)
                return False

            keyword, dname, fname, ext = LogicSubcat.parse_fname(file_path)
            logger.debug('keyword(%s), dname(%s), fname(%s), ext(%s)', keyword, dname, fname, ext)

            if force is not True and entity.sub_status == 3:
                logger.info('SKIP: subfile already exist(key: %s)', keyword)
                return True

            suburl = LogicSubcat.get_suburl(keyword)
            if suburl is None:
                logger.info('failed to find subfile(key:%s)', keyword)
                entity.last_search= datetime.now()
                entity.sub_status = 0
                entity.save()

                if ModelSetting.get_bool('subcat_meta_flag'):
                    LogicSubcat.metadata_refresh(filepath=file_path)

                return True

            logger.info('found sub, try to download(key:%s, url:%s)', keyword, suburl)
            downloaded = LogicSubcat.down_sub(suburl, file_path)
            if ModelSetting.get_bool('subcat_meta_flag'):
                LogicSubcat.metadata_refresh(filepath=file_path)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    @staticmethod
    def process_expire_by_id(data_id):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entity = SubModelItem.get_entity_by_id(data_id)
            if entity is None:
                logger.error('failed to find SubModelItem(id:%s)', data_id)
                return False
            entity.sub_status = 100
            entity.save()
            logger.error('succeed to expire item(id:%s)', data_id)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True


    @staticmethod
    def process_remove_by_id(data_id):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entity = SubModelItem.get_entity_by_id(data_id)
            if entity is None:
                logger.error('failed to find SubModelItem(id:%d)', data_id)
                return False
            entity.remove()
            logger.error('succeed to remove item(id:%s)', data_id)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True


    @staticmethod
    def process_recent():
        try:
            logger.debug('process subcat recent started')
            entities = SubModelItem.get_recent_entities()
            logger.debug('get recent entities(count:%d)', len(entities))
            for entity in entities:
                SubModelItem.print_entity(entity)
                ret = LogicSubcat.process_single_by_id(entity.id)
            return True

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True


    @staticmethod
    def is_sub(fname):
        SUBS = ['.srt', '.ass', '.smi']
        fpath, ext = os.path.splitext(fname)
        if ext in SUBS: return True
        return False

    @staticmethod
    def exist_sub(path, slist):
        for sub in slist:
            spath, ext = os.path.splitext(sub)
            regex = re.compile(spath, re.I)
            if regex.search(path) is not None:
                return True
        return False

    @staticmethod
    def load_flist(path, flist, slist):
        try:
            for f in os.listdir(path):
                fpath = os.path.join(path, f)
                if os.path.isdir(fpath) is True: 
                    load_flist(fpath, flist, slist)
                elif LogicSubcat.is_sub(fpath) is True:
                    slist.append(fpath)
                elif os.path.isfile(fpath) is True:
                    flist.append(fpath)
        except:
            if os.path.isfile(path) is True:
                flist.append(path)

    @staticmethod
    def load_videos(path):
        flist = []
        slist = []
        vlist = []
        
        LogicSubcat.load_flist(path, flist, slist)

        for f in flist:
            if LogicSubcat.exist_sub(f, slist): 
                tlist.remove(f)
            elif os.path.isdir(f) is True:
                tlist.remove(f)
            else:
                keyword, dname, fname, ext = LogicSubcat.parse_fname(f)
                entity = SubModelItem.get_entity(keyword)
                if entity is None:
                    entity = SubModelItem(keyword, dname, fname+ext)
                vlist.append(entity)

        return vlist

    @staticmethod
    def manual_execute(path):
        try:
            logger.debug('subcat_test: target_path(%s)', path)

            if os.path.exists(path) is False:
                logger.warning('target does not exist(path:%s)', path)
                return False

            vlist = LogicSubcat.load_videos(path)

            for entity in vlist:
                SubModelItem.print_entity(entity)
                if entity.sub_status == 3:
                    logger.debug('already exist subfile(%s)', entity.media_path + entity.media_name)
                    continue
                entity.save()
                suburl = LogicSubcat.get_suburl(entity.keyword)
                if suburl is None:
                    logger.info('failed to find subfile(key:%s)', entity.keyword)
                    if ModelSetting.get_bool('subcat_meta_flag'):
                        LogicSubcat.metadata_refresh(filepath=entity.media_path + entity.media_name)
                    continue

                logger.info('found sub, try to download(key:%s, url:%s)', entity.keyword, suburl)
                downloaded = LogicSubcat.down_sub(suburl, entity.media_path + entity.media_name)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    @staticmethod
    def one_execute():
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entities = SubModelItem.get_recent_entities()
            logger.debug('get recent entities(count:%d)', len(entities))
            for entity in entities:
                SubModelItem.print_entity(entity)
                ret = LogicSubcat.process_single_by_id(entity.id)

            logger.debug('%s %s END', __name__, sys._getframe().f_code.co_name)
            return True

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    @staticmethod
    def force_execute():
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entities = SubModelItem.get_all_entities()
            logger.debug('get all entities(count:%d)', len(entities))
            for entity in entities:
                SubModelItem.print_entity(entity)
                ret = LogicSubcat.process_single_by_id(entity.id)

            logger.debug('%s %s END', __name__, sys._getframe().f_code.co_name)
            return True

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    ################## FOR PLEX  by soju6jan
    # SJVA.bundle를 사용하여 라이브러리에 있는지 확인한다.
    @staticmethod
    def is_exist_in_library_using_bundle(filepath):
        try:
            url = '%s/:/plugins/com.plexapp.plugins.SJVA/function/count_in_library?filename=%s&X-Plex-Token=%s' % (PlexModelSetting.get('server_url'), urllib.quote(filepath.encode('utf8')), PlexModelSetting.get('server_token'))
            data = requests.get(url).content
            if data == '0':
                return False
            else:
                try:
                    tmp = int(data)
                    if tmp > 0:
                        return True
                except:
                    return False
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def get_library_key_using_bundle(filepath, section_id=-1):
        try:
            url = '%s/:/plugins/com.plexapp.plugins.SJVA/function/db_handle?action=get_metadata_id_by_filepath&args=%s&X-Plex-Token=%s' % (PlexModelSetting.get('server_url'), urllib.quote(filepath.encode('utf8')), PlexModelSetting.get('server_token'))
            data = requests.get(url).content
            return data
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    
    # 메타 아이디로 파일목록을 받는다. 한편에 여러 파일이 있는경우 순서대로 출력한다.
    @staticmethod
    def get_filepath_list_by_metadata_id_using_bundle(metadata_id):
        try:
            url = '%s/:/plugins/com.plexapp.plugins.SJVA/function/db_handle?action=get_filepath_list_by_metadata_id&args=%s&X-Plex-Token=%s' % (PlexModelSetting.get('server_url'), metadata_id, PlexModelSetting.get('server_token'))
            data = requests.get(url).content
            ret = [x.strip() for x in data.split('\n')]
            return ret
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    

    @staticmethod
    def metadata_refresh(filepath=None, metadata_id=None):
        try:
            if metadata_id is None:
                if filepath is not None:
                    metadata_id = LogicSubcat.get_library_key_using_bundle(filepath)
            if metadata_id is None:
                return False   
            url = '%s/library/metadata/%s/refresh?X-Plex-Token=%s'  % (PlexModelSetting.get('server_url'), metadata_id, PlexModelSetting.get('server_token'))
            data = requests.put(url).content
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return False
