# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback

# third-party
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify, session, send_from_directory 
from flask_socketio import SocketIO, emit, send
from flask_login import login_user, logout_user, current_user, login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data, socketio, check_api
from framework.util import Util
from system.model import ModelSetting as SystemModelSetting

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)
from .model import ModelSetting
from .logic import Logic
from .logic_download import LogicDownload
from .logic_subcat import LogicSubcat

#########################################################

blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

menu = {
    'main' : [package_name, u'AV'],
    'sub' : [
        ['download', u'다운로드 파일처리'], ['subcat', u'자막다운로드'], ['log', u'로그']
    ],
    'category' : 'fileprocess', 
    'sub2' : {
        'download' : [
            ['setting', u'설정'], ['list', u'처리결과']
        ],
        'subcat' : [
            ['setting', u'설정'], ['list', u'목록']
        ]
    },
}

plugin_info = {
    'version' : '0.1.0.0',
    'name' : 'fileprocess_av',
    'category_name' : 'fileprocess',
    'developer' : 'soju6jan',
    'description' : u'파일처리 - AV',
    'home' : 'https://github.com/soju6jan/fileprocess_av',
    'more' : '',
}

def plugin_load():
    Logic.plugin_load()

def plugin_unload():
    Logic.plugin_unload()



#########################################################
# WEB Menu   
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/download/list' % package_name)

@blueprint.route('/<sub>', methods=['GET', 'POST'])
@login_required
def first_menu(sub): 
    logger.debug('FM: sub(%s)', sub)
    if sub == 'download':
        return redirect('/%s/%s/list' % (package_name, sub))
    elif sub == 'subcat':
        return redirect('/%s/%s/list' % (package_name, sub))
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


@blueprint.route('/<sub>/<sub2>')
@login_required
def second_menu(sub, sub2):
    try:
        arg = ModelSetting.to_dict()
        arg['sub'] = sub
        job_id = '%s_%s' % (package_name, sub)
        if sub == 'download':
            if sub2 == 'setting':
                arg['scheduler'] = str(scheduler.is_include(job_id))
                arg['is_running'] = str(scheduler.is_running(job_id))
                return render_template('{package_name}_{sub}_{sub2}.html'.format(package_name=package_name, sub=sub, sub2=sub2), arg=arg)
            elif sub2 == 'list':
                return render_template('{package_name}_{sub}_{sub2}.html'.format(package_name=package_name, sub=sub, sub2=sub2), arg=arg)
        elif sub == 'subcat':
            logger.debug('SUB %s %s %s', package_name, sub, sub2)
            if sub2 == 'setting':
                arg['scheduler'] = str(scheduler.is_include(job_id))
                arg['is_running'] = str(scheduler.is_running(job_id))
                return render_template('{package_name}_{sub}_{sub2}.html'.format(package_name=package_name, sub=sub, sub2=sub2), arg=arg)
            elif sub2 == 'list':
                logger.debug('SUB %s %s %s', package_name, sub, sub2)
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
        return render_template('sample.html', title='%s - %s' % (package_name, sub))
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())
    

#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    logger.debug('AJAX %s %s', package_name, sub)
    try:
        # global
        if sub == 'setting_save':
            ret = ModelSetting.setting_save(request)
            return jsonify(ret)
        elif sub == 'scheduler':
            sub = request.form['sub']
            go = request.form['scheduler']
            logger.debug('scheduler :%s', go)
            if go == 'true':
                Logic.scheduler_start(sub)
            else:
                Logic.scheduler_stop(sub)
            return jsonify(go)
        elif sub == 'reset_db':
            sub = request.form['sub']
            ret = Logic.reset_db(sub)
            return jsonify(ret)
        elif sub == 'one_execute':
            sub = request.form['sub']
            ret = Logic.one_execute(sub)
            return jsonify(ret)
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())  


@blueprint.route('/ajax/<sub>/<sub2>', methods=['GET', 'POST'])
@login_required
def second_ajax(sub, sub2):
    try:
        if sub == 'download':
            return LogicDownload.process_ajax(sub2, request)
        elif sub == 'subcat':
            return LogicSubcat.process_ajax(sub2, request)
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())