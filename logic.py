# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import threading

# third-party

# sjva 공용
from framework import db, scheduler, path_app_root, path_data
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem, SubModelItem
from .logic_download import LogicDownload
from .logic_subcat import LogicSubcat
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

        'normal_use' : 'False',
        'normal_download_path' : '',
        'normal_target_path' : '',
        'normal_temp_path' : '',
        'normal_min_size' : '100',

        'subcat_use' : 'False',
        'subcat_interval' : '120',
        'subcat_url' : 'https://www.subtitlecat.com',
        'subcat_time_period' : '24',
        'subcat_day_limit' : '30',
        'subcat_tmp_path' : os.path.join(path_data, 'tmp'),
        'subcat_langs' : 'Korean',
        'subcat_subext' : '.ko.srt',
        'subcat_meta_flag' : 'False',
        'subcat_manual_path' : '',
        'subcat_include_manual_path_in_scheduler' : 'True',
        'subcat_plex_path_rule' : '',
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
            
            # 기능별로
            if ModelSetting.get_bool('auto_start'):
                Logic.scheduler_start('download')
            if ModelSetting.get_bool('subcat_use'):
                Logic.scheduler_start('subcat')

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
    def scheduler_start(sub):
        try:
            job_id = '%s_%s' % (package_name, sub)
            if sub == 'download':
                job = Job(package_name, job_id, ModelSetting.get('interval'), Logic.scheduler_function, u"AV 파일처리", False, args=sub)
            elif sub == 'subcat':
                job = Job(package_name, job_id, ModelSetting.get('subcat_interval'), Logic.scheduler_function, u"AV 자막다운로드", False, args=sub)
            scheduler.add_job_instance(job)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_stop(sub):
        try:
            job_id = '%s_%s' % (package_name, sub)
            scheduler.remove_job(job_id)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_function(sub):
        if sub == 'download':
            LogicDownload.scheduler_function()
        elif sub == 'subcat':
            logger.debug('1111111111111111111')
            LogicSubcat.scheduler_function()


    @staticmethod
    def reset_db(sub):
        logger.debug('reset db:%s', sub)
        if sub == 'download':
            return LogicDownload.reset_db()
        elif sub == 'subcat':
            return LogicSubcat.reset_db()
        return False


    @staticmethod
    def one_execute(sub):
        logger.debug('one_execute :%s', sub)
        try:
            job_id = '%s_%s' % (package_name, sub)
            if scheduler.is_include(job_id):
                if scheduler.is_running(job_id):
                    ret = 'is_running'
                else:
                    scheduler.execute_job(job_id)
                    ret = 'scheduler'
            else:
                def func():
                    time.sleep(2)
                    Logic.scheduler_function(sub)
                threading.Thread(target=func, args=()).start()
                ret = 'thread'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'
        return ret
    """        
    @staticmethod
    def process_telegram_data(data):
        try:
            logger.debug(data)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    """

    @staticmethod
    def migration():
        try:
            pass
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    ##################################################################################

    

    
