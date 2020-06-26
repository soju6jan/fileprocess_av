# -*- coding: utf-8 -*-
#########################################################
# python
import traceback
from datetime import datetime,timedelta
import json
import os
import re

# third-party
from sqlalchemy import or_, and_, func, not_, desc
from sqlalchemy.orm import backref

# sjva 공용
from framework import app, db, path_app_root
from framework.util import Util

# 패키지
from .plugin import logger, package_name

app.config['SQLALCHEMY_BINDS'][package_name] = 'sqlite:///%s' % (os.path.join(path_app_root, 'data', 'db', '%s.db' % package_name))
#########################################################
        
class ModelSetting(db.Model):
    __tablename__ = '%s_setting' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String, nullable=False)
 
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        return {x.name: getattr(self, x.name) for x in self.__table__.columns}

    @staticmethod
    def get(key):
        try:
            return db.session.query(ModelSetting).filter_by(key=key).first().value.strip()
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
            
    
    @staticmethod
    def get_int(key):
        try:
            return int(ModelSetting.get(key))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_bool(key):
        try:
            return (ModelSetting.get(key) == 'True')
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def set(key, value):
        try:
            item = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            if item is not None:
                item.value = value.strip()
                db.session.commit()
            else:
                db.session.add(ModelSetting(key, value.strip()))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def to_dict():
        try:
            ret = Util.db_list_to_dict(db.session.query(ModelSetting).all())
            ret['package_name'] = package_name
            return ret 
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())


    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                if key in ['scheduler', 'is_running']:
                    continue
                if key.startswith('global_'):
                    continue
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True                  
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug('Error Key:%s Value:%s', key, value)
            return False

    @staticmethod
    def get_list(key):
        try:
            value = ModelSetting.get(key)
            values = [x.strip().strip() for x in value.replace('\n', '|').split('|')]
            values = Util.get_list_except_empty(values)
            return values
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.error('Error Key:%s Value:%s', key, value)

       
class ModelItem(db.Model):
    __tablename__ = '%s_item' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    reserved = db.Column(db.JSON)


    av_type = db.Column(db.String)
    is_file = db.Column(db.Boolean)
    
    source_dir = db.Column(db.String)
    source_filename = db.Column(db.String)
    source_path = db.Column(db.String)
    move_type = db.Column(db.Integer) # -1, 0:정상, 1:타입불일치, 2:중복삭제 
    # uncensored  0:정상, 1:no_type 2:중복삭제 3:유저타겟

    target_dir = db.Column(db.String)
    target_filename = db.Column(db.String)
    target_path = db.Column(db.String)

    log = db.Column(db.String)

    def __init__(self, av_type, source_dir, source_filename):
        self.av_type = av_type
        self.created_time = datetime.now()
        self.is_file = True
        self.source_dir = source_dir
        self.source_filename = source_filename
        self.move_type = -1


    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') 
        return ret
    
    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def web_list(req):
        try:
            ret = {}
            page = 1
            page_size = ModelSetting.get_int('web_page_size')
            job_id = ''
            search = ''
            if 'page' in req.form:
                page = int(req.form['page'])
            if 'search_word' in req.form:
                search = req.form['search_word']
            option = req.form['option']
            order = req.form['order'] if 'order' in req.form else 'desc'
            av_type = req.form['av_type']

            query = ModelItem.make_query(search=search, av_type=av_type, option=option, order=order)
            count = query.count()
            query = query.limit(page_size).offset((page-1)*page_size)
            logger.debug('ModelItem count:%s', count)
            lists = query.all()
            ret['list'] = [item.as_dict() for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', av_type='all', option='all', order='desc'):
        query = db.session.query(ModelItem)
        if search is not None and search != '':
            if search.find('|') != -1:
                tmp = search.split('|')
                conditions = []
                for tt in tmp:
                    if tt != '':
                        conditions.append(ModelItem.source_filename.like('%'+tt.strip()+'%') )
                query = query.filter(or_(*conditions))
            elif search.find(',') != -1:
                tmp = search.split(',')
                for tt in tmp:
                    if tt != '':
                        query = query.filter(ModelItem.source_filename.like('%'+tt.strip()+'%'))
            else:
                query = query.filter(or_(ModelItem.source_filename.like('%'+search+'%'), ModelItem.target_filename.like('%'+search+'%')))

        if av_type != 'all':
            query = query.filter(ModelItem.av_type == av_type)

        if option != 'all':
            query = query.filter(ModelItem.move_type == option)

        if order == 'desc':
            query = query.order_by(desc(ModelItem.id))
        else:
            query = query.order_by(ModelItem.id)

        return query 


class SubModelItem(db.Model):
    __tablename__ = '%s_sub_item' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    reserved = db.Column(db.JSON)

    keyword    = db.Column(db.String)
    media_path = db.Column(db.String)
    media_name = db.Column(db.String)

    last_search= db.Column(db.DateTime) # 최근검색시간
    search_cnt = db.Column(db.Integer)  # 시도횟수

    sub_status = db.Column(db.Integer)  # 0.자막없음, 1:타겟자막없음, 2:자막있음, 3:자막다운완료, 99:검색실패, 100:기간만료
    sub_name   = db.Column(db.String)
    sub_url    = db.Column(db.String)   # 자막파일url

    plex_section_id = db.Column(db.String)
    plex_metakey    = db.Column(db.String)

    #def __init__(self, keyword, media_path, media_name):
    def __init__(self, fullpath):
        self.keyword, dirname, name, ext = SubModelItem.parse_fname(fullpath)
        self.created_time = datetime.now()
        #self.media_path = media_path
        self.media_path = fullpath
        self.media_name = name + ext
        self.search_cnt = 0
        self.last_search= datetime.now()
        self.sub_status = 0
        self.sub_url  = None
        self.sub_name  = None
        self.plex_section_id = None
        self.plex_metakey = None


    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') 
        ret['last_search'] = self.last_search.strftime('%m-%d %H:%M:%S') 
        ret['media_path'] = os.path.dirname(self.media_path)
        return ret
    
    def remove(self):
        try:
            db.session.delete(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    def sub_status_to_str(self):
        if self.sub_status == 0:
            return '자막없음'
        elif self.sub_status == 1:
            return '타겟자막없음'
        elif self.sub_status == 2:
            return '자막있음'
        elif self.sub_status == 3:
            return '자막다운완료'
        elif self.sub_status == 99:
            return '검색실패'
        elif self.sub_status == 100:
            return '만료'
        else:
            return '--'

    @staticmethod
    def create(fullpath):
        try:
            entity = SubModelItem.get_entity_by_fullpath(fullpath)
            if entity is None:
                entity = SubModelItem(fullpath)
                entity.save()
                return entity
            return None
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def print_entity(entity):
        try:
            logger.debug('------------------------------------------------')
            logger.debug('id              : %s', entity.id)
            logger.debug('created_time    : %s', entity.created_time)
            logger.debug('keyword         : %s', entity.keyword)
            logger.debug('media_path      : %s', entity.media_path)   
            logger.debug('media_name      : %s', entity.media_name)   
            logger.debug('search_cnt      : %s', entity.search_cnt)
            logger.debug('last_search     : %s', entity.last_search)
            logger.debug('sub_status      : %s(%s)', entity.sub_status_to_str(), entity.sub_status)
            logger.debug('plex_section_id : %s', entity.plex_section_id if entity.plex_section_id is not None else 'None')
            logger.debug('plex_metakey    : %s', entity.plex_metakey if entity.plex_metakey is not None else 'None')
            logger.debug('------------------------------------------------')
        except:
            return False

    # keyword, 디렉토리, 파일명(확장자제외), 확장자
    @staticmethod
    def parse_fname(path):
        name, ext = os.path.splitext(os.path.basename(path))
        dirname = os.path.dirname(path)
        key = name.split('[')[0].strip()
        if key[-3:-1] == 'cd':
            key = key[:-3]
        return key, dirname, name, ext

    @staticmethod
    def add_subcat_queue(target_filepath):
        try:
            keyword, dname, fname, ext = SubModelItem.parse_fname(target_filepath)
            item = SubModelItem(keyword, dname, fname+ext)
            item.save()
            logger.debug('new file added(%s)', target_filepath)
            return True
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    # 동일 키워드 이름이 다른 파일들이 많은경우 보장안됨.
    """
    @staticmethod
    def get_entity(keyword):
        try:
            entity = db.session.query(SubModelItem).filter_by(keyword=keyword).with_for_update().first()
            if entity is not None:
                return entity
        except:
            return None
    """

    @staticmethod
    def get_entity_by_id(data_id):
        try:
            entity = db.session.query(SubModelItem).filter_by(id=data_id).with_for_update().first()
            if entity is not None:
                return entity
        except:
            return None

    @staticmethod
    def get_entity_by_fullpath(path):
        try:
            entity = db.session.query(SubModelItem).filter_by(media_path=path).with_for_update().first()
            if entity is not None:
                return entity
        except:
            return None

    @staticmethod
    def get_recent_entities():
        try:
            currtime = datetime.now()

            time_period = ModelSetting.get_int('subcat_time_period')
            day_limit   = ModelSetting.get_int('subcat_day_limit')
            logger.debug('get recent list: period(%d), limit(%d)', time_period, day_limit)

            query = db.session.query(SubModelItem)

            query = query.filter(SubModelItem.sub_status!=3)     # 자막다운받은경우제외
            query = query.filter(SubModelItem.sub_status!=100)   # 만료된경우제외

            ptime = currtime + timedelta(hours=-time_period)
            #ptime = currtime + timedelta(minutes=-10) #임시코드
            query = query.filter(or_(SubModelItem.last_search < ptime, SubModelItem.search_cnt == 0))   # 최근검색한 목록 제외
            count = query.count()
            if count == 0: return []
            entities = query.all()

            for entity in entities:
                pday = entity.created_time + timedelta(days=day_limit)
                if currtime > pday:
                    lists.remove(entity)
                    entity.sub_status = 100
                    entity.save()

            return entities

        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_all_entities():
        try:
            query = db.session.query(SubModelItem)
            query = query.filter(SubModelItem.sub_status!=3)     # 자막다운받은경우제외
            count = query.count()
            entities = query.all()
            return entities

        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def web_list(req):
        try:
            ret = {}
            page = 1
            page_size = ModelSetting.get_int('web_page_size')
            job_id = ''
            search = ''
            if 'page' in req.form:
                page = int(req.form['page'])
            if 'search_word' in req.form:
                search = req.form['search_word']
            option = req.form['option'] if 'option' in req.form else 'all'
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = SubModelItem.make_query(search=search, option=option, order=order)
            count = query.count()
            query = query.limit(page_size).offset((page-1)*page_size)
            logger.debug('SubModelItem count:%s', count)
            lists = query.all()
            ret['list'] = [item.as_dict() for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception, e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', option='all', order='desc'):
        query = db.session.query(SubModelItem)
        if search is not None and search != '':
            if search.find('|') != -1:
                tmp = search.split('|')
                conditions = []
                for tt in tmp:
                    if tt != '':
                        conditions.append(SubModelItem.media_name.like('%'+tt.strip()+'%') )
                query = query.filter(or_(*conditions))
            elif search.find(',') != -1:
                tmp = search.split(',')
                for tt in tmp:
                    if tt != '':
                        query = query.filter(SubModelItem.media_name.like('%'+tt.strip()+'%'))
            else:
                query = query.filter(SubModelItem.media_name.like('%'+search+'%'))

        if option != 'all':
            query = query.filter(SubModelItem.sub_status == option)

        if order == 'desc':
            query = query.order_by(desc(SubModelItem.id))
        else:
            query = query.order_by(SubModelItem.id)

        return query    
