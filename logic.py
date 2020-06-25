# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import threading

# third-party

# sjva 공용
from framework import db, scheduler, path_app_root
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem, SubModelItem
from .logic_normal import LogicNormal, ModelItem
from .logic_subcat import LogicSubcat, SubModelItem
#########################################################


class Logic(object):
    db_default = { 
        'db_version' : '1',
        'auto_start' : 'False',
        'interval' : '10',
        'web_page_size' : '30',

        'censored_use' : 'False',
        'censored_download_path' : '',
        'censored_target_path' : '',
        'censored_temp_path' : '',
        'censored_min_size' : '300',
        'censored_use_meta' : '0',
        'censored_meta_dmm_path' : '',
        'censored_meta_javdb_path' : '',
        'censored_meta_no_path' : '',
        'include_original_filename' : 'True',

        'uncensored_use' : 'False',
        'uncensored_use_meta' : 'False',
        'uncensored_download_path' : '',
        'uncensored_target_path' : '',
        'uncensored_temp_path' : '',
        'uncensored_min_size' : '100',
        'uncensored_meta_match_path' : '',
        'uncensored_meta_unmatch_path' : '',
        
        'western_use' : 'False',
        'western_download_path' : '',
        'western_remove_ext' : '',
        'western_use_meta' : '0',
        'western_meta_match_path' : '',
        'western_target_path' : '',
        'western_temp_path' : '',

        'subcat_use' : 'False',
        'subcat_url' : 'https://www.subtitlecat.com',
        'subcat_time_period' : '24',
        'subcat_day_limit' : '30',
        'subcat_tmp_path' : '',
        'subcat_langs' : 'Korean|English',
        'subcat_subext' : '.ko.srt',
        'subcat_meta_flag' : 'False',
        'subcat_manual_path' : '',
        
        'normal_use' : 'False',
        'normal_download_path' : '',
        'normal_target_path' : '',
        'normal_temp_path' : '',
        'normal_min_size' : '100',
        
    }

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
            
            Logic.migration()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            logger.debug('%s plugin_load', package_name)
            Logic.db_init()
            if ModelSetting.query.filter_by(key='auto_start').first().value == 'True':
                Logic.scheduler_start()
            # 편의를 위해 json 파일 생성
            from plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_start():
        try:
            interval = ModelSetting.query.filter_by(key='interval').first().value
            job = Job(package_name, package_name, interval, Logic.scheduler_function, u"AV 파일처리", False)
            scheduler.add_job_instance(job)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    
    @staticmethod
    def scheduler_stop():
        try:
            scheduler.remove_job(package_name)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_function():
        LogicNormal.scheduler_function()


    @staticmethod
    def reset_db():
        try:
            db.session.query(ModelItem).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @staticmethod
    def one_execute():
        try:
            if scheduler.is_include(package_name):
                if scheduler.is_running(package_name):
                    ret = 'is_running'
                else:
                    scheduler.execute_job(package_name)
                    ret = 'scheduler'
            else:
                def func():
                    time.sleep(2)
                    Logic.scheduler_function()
                threading.Thread(target=func, args=()).start()
                ret = 'thread'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def subcat_manual_execute(path):
        try:
            th = threading.Thread(target=LogicSubcat.handler_function, args=('manual_execute', path,))
            th.start()
            ret = 'thread'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def subcat_one_execute():
        try:
            th = threading.Thread(target=LogicSubcat.handler_function, args=('one_execute', '',))
            th.start()
            ret = 'thread'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def subcat_force_execute():
        try:
            th = threading.Thread(target=LogicSubcat.handler_function, args=('force_execute', '',))
            th.start()
            ret = 'thread'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def proc_single(data_id):
        try:
            logger.debug('%s STARTED', __name__)
            th = threading.Thread(target=LogicSubcat.handler_function, args=('proc_single',data_id,))
            th.start()
            ret = 'Success'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def proc_expire(data_id):
        try:
            logger.debug('%s STARTED', __name__)
            th = threading.Thread(target=LogicSubcat.handler_function, args=('proc_expire',data_id,))
            th.start()
            ret = 'Success'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret


    @staticmethod
    def proc_remove(data_id):
        try:
            logger.debug('%s STARTED', __name__)
            th = threading.Thread(target=LogicSubcat.handler_function, args=('proc_remove',data_id,))
            th.start()
            ret = 'Success'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret

    @staticmethod
    def subcat_reset_db():
        try:
            db.session.query(SubModelItem).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @staticmethod
    def process_telegram_data(data):
        try:
            logger.debug(data)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def migration():
        try:
            pass
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

