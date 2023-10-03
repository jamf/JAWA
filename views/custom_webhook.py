# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2022 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

from collections import defaultdict
from flask import (Blueprint, redirect, render_template,
                   request, session, url_for)
import json
import os
from werkzeug.utils import secure_filename


from bin.view_modifiers import response
from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)

blueprint = Blueprint('custom_webhook', __name__, template_folder='templates')

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
okta_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'okta_json.json'))
okta_verification_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'okta_verification.py'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@blueprint.route('/webhooks/custom', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/home.html')
def custom_webhook():
    if 'username' not in session:
        return redirect(url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    custom_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "custom":
            custom_webhooks_list.append(each_webhook)

    return {'username': session.get('username'),
            'custom_list': custom_webhooks_list}


@blueprint.route('/webhooks/custom/edit', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/edit.html')
def edit_webhook():
    if 'username' not in session:
        return redirect(url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    name = request.args.get('name')
    logthis.info(f"Checking for custom webhook '{name}'")
    with open(webhooks_file) as fin:
        webhooks_json = json.load(fin)
    check_for_name = [True for each_webhook in webhooks_json if each_webhook['name'] == name]
    logthis.info(f"Name exists? {check_for_name}")
    if not check_for_name:
        logthis.info(f"JAWA is not aware of any custom webhook named {name}")
        return redirect(url_for('custom_webhook.custom_webhook'))
    if request.method == 'POST':
        button_choice = request.form.get('button_choice')
        if button_choice == 'Delete':
            logthis.info(f"{session.get('username')} is considering deleting a custom webhook ({name})...")
            return redirect(url_for('webhooks.delete_webhook', target_webhook=name))
        for each_webhook in webhooks_json:
            if each_webhook['name'] == name:
                logthis.info(f"{session.get('username')} is editing a custom webhook ({name})...")
                output = request.form.get('output')
                new_custom_name = request.form.get('custom_name')
                if not new_custom_name:
                    new_custom_name = name
                description = request.form.get('description')
                if request.form.get('basic'):
                    new_webhook_user = request.form.get('username', 'null')
                    new_webhook_pass = request.form.get('password', 'null')
                else:
                    new_webhook_user = 'null'
                    new_webhook_pass = 'null'
                if request.form.get('custom'):
                    new_webhook_apikey = request.form.get('api_key', 'null')
                else:
                    new_webhook_apikey = 'null'
                if new_webhook_user and new_webhook_user != "":
                    each_webhook['webhook_username'] = new_webhook_user
                else:
                    each_webhook['webhook_username'] = 'null'
                if new_webhook_pass and new_webhook_pass != "":
                    each_webhook['webhook_password'] = new_webhook_pass
                else:
                    each_webhook['webhook_password'] = 'null'
                if new_webhook_apikey and new_webhook_apikey != "":
                    each_webhook['api_key'] = new_webhook_apikey
                else:
                    each_webhook['webhook_password'] = 'null'
                if request.files.get('new_file'):
                    new_script = request.files.get('new_file')
                    owd = os.getcwd()
                    os.chdir(scripts_dir)

                    if ' ' in new_script.filename:
                        new_script.filename = new_script.filename.replace(" ", "-")

                    new_filename = f"{new_custom_name}-{new_script.filename}"
                    new_script.save(secure_filename(new_filename))
                    new_filename = os.path.join(scripts_dir, f"{new_custom_name}-{new_script.filename}")
                    os.chmod(new_filename, mode=0o0755)
                    os.chdir(owd)
                    each_webhook['script'] = new_filename

                each_webhook['name'] = new_custom_name
                if description:
                    each_webhook['description'] = description
                each_webhook['webhook_username'] = new_webhook_user
                each_webhook['webhook_password'] = new_webhook_pass
                each_webhook['output'] = output

                with open(webhooks_file, 'w') as fout:
                    json.dump(webhooks_json, fout, indent=4)
                webhook_info = [each_webhook]
                return {"webhooks": "success",
                        "success_msg": f"Edited custom webhook {new_custom_name}.",
                        "username": session.get('username'), 'webhook_info': webhook_info, "webhook_name": new_custom_name,
                        "description": each_webhook.get('description')}
    webhook_info = [each_webhook for each_webhook in webhooks_json if each_webhook['name'] == name]
    return {'username': session.get('username'), 'webhook_name': name, 'webhook_info': webhook_info}


@blueprint.route('/webhooks/custom/new', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/new.html')
def new_webhook():
    if 'username' not in session:
        return redirect(url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    if request.method == 'POST':
        new_custom_name = request.form.get('custom_name')
        description = request.form.get('description')
        output = request.form.get('output')


        if request.form.get('custom_name') != '':
            check = 0
            logthis.info(f"New webhook name: {request.form.get('custom_name')}")

            with open(webhooks_file, 'r') as json_file:
                webhooks_json = json.load(json_file)
            if webhooks_json:
                for each_webhook in webhooks_json:

                    if each_webhook.get('name') == new_custom_name:
                        check = 1
            owd = os.getcwd()
            if not os.path.isdir(scripts_dir):
                os.mkdir(scripts_dir)
            os.chdir(scripts_dir)
            target_file = request.files.get('new_file')

            if ' ' in target_file.filename:
                target_file.filename = target_file.filename.replace(" ", "-")

            new_filename = f"{new_custom_name}-{target_file.filename}"
            target_file.save(secure_filename(new_filename))
            new_filename = os.path.join(scripts_dir, f"{new_custom_name}-{target_file.filename}")
            os.chmod(new_filename, mode=0o0755)
            os.chdir(owd)
            if check != 0:
                error_message = "Name already exists!"
                logthis.info(f"Could not create new webhook. Message: {error_message}")
                return {"error": error_message, "username": session.get('username'), 'name': new_custom_name,
                        'description': description}
            new_webhook_user = request.form.get('username', 'null')
            if not new_webhook_user:
                new_webhook_user = "null"
            new_webhook_pass = request.form.get('password', 'null')
            if not new_webhook_pass:
                new_webhook_pass = "null"
            if request.form.get('custom'):
                api_key = request.form.get('api_key', 'null')
            else:
                api_key = 'null'
            webhooks_json.append({"url": str(session['url']),
                                  "jawa_admin": str(session['username']),
                                  "name": new_custom_name,
                                  "webhook_username": new_webhook_user,
                                  "webhook_password": new_webhook_pass,
                                  "api_key": api_key,
                                  "script": new_filename,
                                  "description": description,
                                  "tag": "custom",
                                  "output": output})

            with open(webhooks_file, 'w') as outfile:
                json.dump(webhooks_json, outfile, indent=4)

            return redirect(url_for('custom_webhook.custom_webhook'))
    return {'username': session.get('username')}
