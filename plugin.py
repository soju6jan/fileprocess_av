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
from framework.common.torrent.process import TorrentProcess



# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)
from .logic import Logic
from .logic_subcat import LogicSubcat
from .model import ModelSetting, ModelItem, SubModelItem
#########################################################

blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

menu = {
    'main' : [package_name, 'AV'],
    'sub' : [
        ['setting', '설정'], ['list', '처리결과'], ['subcat', '자막다운로드'], ['log', '로그']
    ],
    'category' : 'fileprocess'
}

plugin_info = {
    'version' : '0.1.0.0',
    'name' : 'fileprocess_av',
    'category_name' : 'fileprocess',
    'developer' : 'soju6jan',
    'description' : '파일처리 - AV',
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
    return redirect('/%s/list' % package_name)

@blueprint.route('/<sub>', methods=['GET', 'POST'])
@login_required
def first_menu(sub): 
    logger.debug('FM: sub(%s)', sub)
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['package_name']  = package_name
        arg['scheduler'] = str(scheduler.is_include(package_name))
        arg['is_running'] = str(scheduler.is_running(package_name))
        return render_template('{package_name}_{sub}.html'.format(package_name=package_name, sub=sub), arg=arg)
    elif sub == 'list':
        arg = {}
        arg['package_name']  = package_name
        return render_template('{package_name}_{sub}.html'.format(package_name=package_name, sub=sub), arg=arg)
    elif sub == 'subcat':
        return redirect('/%s/%s/list' % (package_name, sub))
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))

@blueprint.route('/<sub>/<sub2>')
@login_required
def second_menu(sub, sub2):
    if sub == 'subcat':
        if sub2 == 'setting' or sub2 == 'list':
            try:
                arg = ModelSetting.to_dict()
                arg['package_name']  = package_name
                logger.debug('SUB %s %s %s', package_name, sub, sub2)
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
    return render_template('sample.html', title='%s - %s' % (package_name, sub))

#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    logger.debug('AJAX %s %s', package_name, sub)
    try:
        if sub == 'setting_save':
            ret = ModelSetting.setting_save(request)
            return jsonify(ret)
        elif sub == 'scheduler':
            go = request.form['scheduler']
            logger.debug('scheduler :%s', go)
            if go == 'true':
                Logic.scheduler_start()
            else:
                Logic.scheduler_stop()
            return jsonify(go)
        elif sub == 'reset_db':
            ret = Logic.reset_db()
            return jsonify(ret)
        elif sub == 'one_execute':
            ret = Logic.one_execute()
            return jsonify(ret)
        elif sub == 'web_list':
            ret = ModelItem.web_list(request)
            return jsonify(ret)
        #for subcat
        elif sub == 'subcat_manual_execute':
            path = request.form['path']
            ret = Logic.subcat_manual_execute(path)
            return jsonify(ret)
        elif sub == 'subcat_one_execute':
            ret = Logic.subcat_one_execute()
            return jsonify(ret)
        elif sub == 'subcat_force_execute':
            ret = Logic.subcat_force_execute()
            return jsonify(ret)
        elif sub == 'subcat_single':
            data_id = request.form['data_id']
            ret = Logic.proc_single(data_id)
            return jsonify(ret)
        elif sub == 'subcat_expire':
            data_id = request.form['data_id']
            ret = Logic.proc_expire(data_id)
            return jsonify(ret)
        elif sub == 'subcat_remove':
            data_id = request.form['data_id']
            ret = Logic.proc_remove(data_id)
            return jsonify(ret)
        elif sub == 'web_sublist':
            ret = SubModelItem.web_sublist(request)
            return jsonify(ret)
        elif sub == 'subcat_reset_db':
            ret = Logic.subcat_reset_db()
            return jsonify(ret)

    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())  
