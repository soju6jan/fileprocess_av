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
from flask import jsonify

try:
    from bs4 import BeautifulSoup
except:
    os.system('pip install bs4')
    from bs4 import BeautifulSoup

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, SubModelItem
#########################################################

class LogicSubcat(object):
    @staticmethod
    def process_ajax(sub, req):
        try:
            if sub == 'click_execute':
                path = req.form['path']
                func_type = req.form['func_type']
                def func():
                    time.sleep(2)
                    LogicSubcat.scheduler_function(func_type=func_type, param=path)
                threading.Thread(target=func, args=()).start()
                ret = 'thread'
                return jsonify(ret)
            elif sub == 'web_list':
                ret = SubModelItem.web_list(req)
                return jsonify(ret)
            elif sub == 'subcat_single':
                data_id = req.form['data_id']
                LogicSubcat.process_single_by_id(data_id, force=True)
                ret = SubModelItem.get_entity_by_id(data_id).as_dict()
                return jsonify(ret)
            elif sub == 'subcat_expire':
                data_id = req.form['data_id']
                entity = SubModelItem.get_entity_by_id(data_id)
                if entity is None:
                    logger.error('failed to find SubModelItem(id:%s)', data_id)
                    return False
                entity.sub_status = 100
                entity.save()
                return jsonify(True)
            elif sub == 'subcat_remove':
                data_id = req.form['data_id']
                entity = SubModelItem.get_entity_by_id(data_id)
                if entity is None:
                    logger.error('failed to find SubModelItem(id:%d)', data_id)
                    return False
                entity.remove()
                return jsonify(True)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            

    @staticmethod
    def scheduler_function(func_type='scheduler', param=None):
        ##LogicSubcat.task(func_type, param)
        #return
        if app.config['config']['use_celery']:
            result = LogicSubcat.task.apply_async((func_type, param))
            result.get()
        else:
            LogicSubcat.task(func_type, param)

    @staticmethod
    def reset_db():
        try:
            db.session.query(SubModelItem).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    #################################################################

    @staticmethod
    @celery.task
    def task(func_type, param):
        # scheduler, path, db_one, db_force
        try:
            logger.debug('%s SUBCAT HANDLER TASK(%s)', __name__, func_type)
            if func_type == 'scheduler':
                LogicSubcat.dblist_execute('db_one')
                #if ModelSetting.get_bool('subcat_include_manual_path_in_scheduler'):
                    #LogicSubcat.manual_execute(param) 
            elif func_type in ['db_one', 'db_force', 'db_force_move']:
                LogicSubcat.dblist_execute(func_type)
            elif func_type == 'path':
                LogicSubcat.manual_execute(ModelSetting.get('subcat_manual_path'))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    


    #################################################################
    # db execute 
    #################################################################
    @staticmethod
    def dblist_execute(func_type):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            if func_type == 'db_one':
                entities = SubModelItem.get_recent_entities()
            elif func_type == 'db_force':
                entities = SubModelItem.get_all_entities()
            elif func_type == 'db_force_move':
                entities = SubModelItem.get_all_entities_with_sub()
            logger.debug('get %s entities(count:%d)', func_type, len(entities))
            for entity in entities:
                SubModelItem.print_entity(entity)
                if func_type == 'db_force_move':
                    ret = LogicSubcat.process_force_move_by_id(entity.id)
                else:
                    ret = LogicSubcat.process_single_by_id(entity.id)

            logger.debug('%s %s END', __name__, sys._getframe().f_code.co_name)
            return True

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    # db 아이템 하나 처리
    @staticmethod
    def process_single_by_id(data_id, force=False):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entity = SubModelItem.get_entity_by_id(data_id)
            if entity is None:
                logger.error('failed to find SubModelItem(id:%d)', id)
                return False
            #file_path = entity.media_path + entity.media_name
            file_path = entity.media_path
            logger.debug('process_single_by_id started(path:%s)', file_path)

            # for test
            #libkey = LogicSubcat.get_library_key_using_bundle(file_path, -1)
            if os.path.isfile(file_path) is False:
                logger.warning('target file does not exist(path:%s)', file_path)
                return False

            #keyword, dname, fname, ext = LogicSubcat.parse_fname(file_path)
            #logger.debug('keyword(%s), dname(%s), fname(%s), ext(%s)', keyword, dname, fname, ext)
            keyword = entity.keyword

            if force is not True and entity.sub_status == 3:
                logger.info('SKIP: subfile already exist(key: %s)', keyword)
                return True

            suburl = LogicSubcat.get_suburl(entity)
            if suburl is None:
                logger.info('failed to find subfile(key:%s)', keyword)
                entity.last_search= datetime.now()
                entity.sub_status = 0
                entity.save()
                logger.debug('suburl is none')
                return True
            else:
                entity.sub_url = suburl
            logger.info('found sub, try to download(key:%s, url:%s)', keyword, suburl)

            #downloaded = LogicSubcat.down_sub(entity)
            ret, sub_filepath = LogicSubcat.down_sub(entity)

            if ModelSetting.get_bool('subcat_meta_flag'):
                LogicSubcat.metadata_refresh(file_path, sub_filepath)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    # 자막파일이 있는 경우 자막/영상 파일 강제이동(목록기반 수동실행)
    @staticmethod
    def process_force_move_by_id(data_id):
        logger.debug('%s %s START', __name__, sys._getframe().f_code.co_name)
        try:
            entity = SubModelItem.get_entity_by_id(data_id)
            if entity is None:
                logger.error('failed to find SubModelItem(id:%d)', id)
                return False
            force_move_flag = ModelSetting.get_bool('subcat_force_move_flag')
            force_move_path = ModelSetting.get('subcat_force_move_path')

            if os.path.isdir(force_move_path) is False:
                logger.warning('invalid target path(%s)', force_move_path)
                return False

            logger.info('FORCE Media/sub file move to: %s', force_move_path)

            old_media_path = entity.media_path
            old_sub_path   = os.path.join(os.path.dirname(old_media_path), entity.sub_name)
            #new_media_path = os.path.join(force_move_path, entity.media_name)
            #new_sub_path   = os.path.join(force_move_path, entity.sub_name)
            # 파일이동시 원본파일 depth 유지
            new_media_path = LogicSubcat.get_new_media_path(old_media_path)
            new_sub_path = os.path.join(os.path.dirname(new_media_path), entity.sub_name)

            # 품번폴더 생성 여부에 따른 처리
            if ModelSetting.get('subcat_create_keyword_folder'):
                new_media_path = os.path.join(os.path.dirname(new_media_path), entity.keyword.upper(), entity.media_name)
                new_sub_path = os.path.join(os.path.dirname(new_media_path), entity.sub_name)

            logger.debug('process_force_move_by_id started(path:%s)', old_media_path)

            if os.path.isfile(old_media_path) is False or os.path.isfile(old_sub_path) is False:
                logger.warning('file does not exist(media:%s,sub:%s)', old_media_path, old_sub_path)
                return False

            if os.path.exists(os.path.dirname(new_media_path)) is False:
                os.makedirs(os.path.dirname(new_media_path))

            # 자막/영상 강제이동 처리
            logger.info('move media file: from(%s) -> to(%s)', old_media_path, new_media_path)
            shutil.move(old_media_path, new_media_path) 
            entity.media_path = new_media_path
            entity.sub_status = 33
            logger.info('move sub   file: from(%s) -> to(%s)', old_sub_path, new_sub_path)
            shutil.move(old_sub_path, new_sub_path)
            entity.save()

            # 강제이동시 Plex Library에서 삭제&새로운경로에 추가되는 영상의 Scan은 Gdrive Scan에 맡김
            """ 
            if ModelSetting.get_bool('subcat_meta_flag'):
                # delete old media from plex
                # 있는걸 지우는 거라, 별도 Thread로 처리할 필요가 없을 듯
                if LogicSubcat.metadata_delete(old_media_path) is False:
                    logger.warning('failed to delete old media from plex(path:%s)', old_media_path)
                    # do nothing

                # refresh가 스캔도 해주나? 
                LogicSubcat.metadata_refresh(new_media_path, new_sub_path)
            """

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

   




    #################################################################
    # subcat core 기능
    #################################################################
    @staticmethod
    def get_response(url):
        logger.debug('get_response 11')
        for i in range(1, 3 + 1):
            try:
                r = requests.get(url)
                if r.status_code == 200 and len(r.text) > 1024: 
                    return r
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        return None
        

    @staticmethod
    def down_sub(entity):
        try:
            #keyword, dname, name, ext = SubModelItem.parse_fname(path)
            #entity = SubModelItem.get_entity(keyword)
            url = entity.sub_url
            keyword = entity.keyword
        
            r = LogicSubcat.get_response(url)
            if r is None:
                logger.error('failed to download subfile(key:%s, url:%s)', keyword, url)
                entity.sub_status = 99
                entity.save()
                return False, None
            name = os.path.splitext(entity.media_name)[0]
            fname = name + ModelSetting.get('subcat_subext')
            tmp_f = os.path.join(ModelSetting.get('subcat_tmp_path'), fname)
            dst_f = os.path.join(os.path.dirname(entity.media_path), fname)
        
            logger.info('download sub to: %s', tmp_f)
            
            f = open(tmp_f, mode='wb')
            size = f.write(r.text.encode('utf-8'))
            f.close()

            # 자막/영상 강제이동 처리
            force_move_flag = ModelSetting.get_bool('subcat_force_move_flag')
            force_move_path = ModelSetting.get('subcat_force_move_path')

            if force_move_flag and os.path.isdir(force_move_path):
                logger.info('FORCE Media/sub file move to: %s', force_move_path)
                
                #new_media_path = os.path.join(force_move_path, entity.media_name)
                new_media_path = LogicSubcat.get_new_media_path(entity.media_path)
                dst_f = os.path.join(os.path.dirname(new_media_path), fname)

                if ModelSetting.get('subcat_create_keyword_folder'):
                    new_media_path = os.path.join(os.path.dirname(new_media_path), keyword.upper(), entity.media_name)
                    dst_f = os.path.join(os.path.dirname(new_media_path), fname)

                logger.info('move media file: from(%s) -> to (%s)', entity.media_path, new_media_path)
                shutil.move(entity.media_path, new_media_path) 

                # 강제이동시 Plex Library에서 삭제&새로운경로에 추가되는 영상의 Scan은 Gdrive Scan에 맡김
                """
                if ModelSetting.get_bool('subcat_meta_flag'):
                    if LogicSubcat.metadata_delete(entity.media_path) is False:
                        logger.warning('failed to delete old media from plex(path:%s)', entity.media_path)
                """
                # update new path
                entity.media_path = new_media_path
                entity.sub_status = 33

            logger.info('move subfile to: %s' % dst_f)
            shutil.move(tmp_f, dst_f)
            #LogicSubcat.metadata_refresh(filepath=path)

            entity.sub_status = 3 if entity.sub_status != 33 else 33
            entity.sub_name = fname
            entity.save()

            return True, dst_f
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return False, None

    # 자막 url 을 찾으면 리턴. 
    @staticmethod
    def get_suburl(entity):
        try:
            key = entity.keyword
            SURL = '/index.php?search={keyword}'
            url = ModelSetting.get('subcat_url') + SURL.format(keyword=key)
            logger.debug('try to search sublist (%s), url(%s)', key, url)

            #entity = SubModelItem.get_entity(key)
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
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())









    #################################################################
    # path execute 
    #################################################################
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
                ret = LogicSubcat.process_single_by_id(entity.id)
            logger.debug('manual_execute end')
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        
        return True

    

    @staticmethod
    def exist_sub(path, slist):
        tmp = os.path.splitext(path)
        for sub in slist:
            spath, ext = os.path.splitext(sub)
            if spath.startswith(tmp[0]):
                return sub
        return False


    # jpg, nfo 등이 있을 수 있음
    @staticmethod
    def load_flist(path, flist, slist):
        logger.debug('load_flist : %s', path)
        try:
            if os.path.isdir(path):
                for f in os.listdir(path):
                    fpath = os.path.join(path, f)
                    if os.path.isdir(fpath) is True: 
                        LogicSubcat.load_flist(fpath, flist, slist)
                    else:
                        tmp = os.path.splitext(f)
                        if len(tmp) != 2:
                            continue
                        if tmp[1].lower() in ['.srt', '.ass', '.smi']:
                            slist.append(fpath)
                        elif tmp[1].lower() in ['.mp4', '.mkv', '.avi']:
                            flist.append(fpath)
            else:
                flist.append(path)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    # 자막이 있더라도 모든 비디오 파일을 넣는다
    # 안그러면 매번 탐색
    @staticmethod
    def load_videos(path):
        flist = []  # 파일의 풀경로. 자막을 제외한 모든 파일
        slist = []  # 자막 목록
        vlist = []
        
        LogicSubcat.load_flist(path, flist, slist)

        logger.debug('flist : %s', len(flist))
        logger.debug('slist : %s', len(slist))

        for f in flist:
            #if LogicSubcat.exist_sub(f, slist): 
            #    tlist.remove(f)
            #elif os.path.isdir(f) is True:
            #    tlist.remove(f)
            #else:
            #    keyword, dname, fname, ext = SubModelItem.parse_fname(f)
            #    entity = SubModelItem.get_entity(keyword)
            #    if entity is None:
            #        entity = SubModelItem(keyword, dname, fname+ext)
            #    vlist.append(entity)
            entity = SubModelItem.create(f)
            if entity is not None:
                ret = LogicSubcat.exist_sub(f, slist)
                if ret:
                    entity.sub_status = 3
                    entity.sub_name = os.path.basename(ret)
                    entity.save()
                vlist.append(entity)
        logger.debug('video list :%s', len(vlist))
        return vlist

    
    @staticmethod
    def metadata_refresh(filepath, sub_filepath):
        try:
            logger.debug('metadata_refresh:%s', filepath)
            filepath = LogicSubcat.get_plex_path(filepath)
            sub_filepath = LogicSubcat.get_plex_path(sub_filepath)
            logger.debug('plexpath:%s', filepath)
            import threading, time, plex
            def func(filepath, sub_filepath):
                for i in range(5):
                    time.sleep(60)
                    logger.debug('plex:%s', filepath)
                    if plex.LogicNormal.os_path_exists(sub_filepath):
                        logger.debug('plex file exist')
                        plex.LogicNormal.metadata_refresh(filepath=filepath)
                        break
                    logger.debug('plex not file exist')
            t = threading.Thread(target=func, args=(filepath,sub_filepath))
            t.setDaemon(True)
            t.start()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return False

    @staticmethod
    def metadata_delete(old_media_path):
        try:
            logger.debug('try to delete metadata for:%s', old_media_path)
            filepath = LogicSubcat.get_plex_path(old_media_path)
            import threading, time, plex
            from plex.model import ModelSetting as PlexModelSetting
            # get metaid
            metaid = plex.LogicNormal.get_library_key_using_bundle(filepath)
            if metaid is None:
                logger.error('failed to get metadata_id(path:%s)', filepath)
                return False

            # request to delete old media from plex
            murl = '/library/metadata/{metaid}/?includeExternalMedia=1&X-Plex-Token={token}'
            url = PlexModelSetting.get('server_url') + murl.format(metaid=metaid, token=PlexModelSetting.get('server_token'))
            logger.debug('delete url:%s', url)
            r = requests.delete(url)
            if r.status_code != 200:
                logger.error('failed to delete media from plex(meta_id:%s, path:%s)', metaid, filepath)
                return False
            logger.info('media deleted(meta_id:%s, path:%s)', metaid, filepath)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return False

    @staticmethod
    def get_plex_path(fpath):
        tmp1 = ModelSetting.get('subcat_plex_path_rule')
        tmp2 = tmp1.split('|') 
        if tmp1 == '' or len(tmp2) != 2:
            return fpath
        ret = fpath.replace(tmp2[0], tmp2[1])
        ret = ret.replace('\\', '/') if tmp2[1][0] == '/' else ret.replace('/', '\\')
        return ret

    @staticmethod
    def get_new_media_path(old_media_path):
        move_path = ModelSetting.get('subcat_force_move_path')
        path_rules = ModelSetting.get_list('subcat_force_move_path_rule')

        if move_path.endswith('/'): move_path = move_path[:-1]
        for path in path_rules:
            if path.endswith('/'): path = path[:-1]
            if old_media_path.startswith(path):
                return old_media_path.replace(path, move_path)
        return os.path.join(move_path, os.path.basename(old_media_path))
