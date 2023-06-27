# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2023 Jamf.  All rights reserved.
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
from flask import (Blueprint, escape, redirect, render_template,
                   request, session, url_for)
import json
import os
import re
import requests
from werkzeug.utils import secure_filename

from bin.tokens import validate_token, get_token
from bin.view_modifiers import response
from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
verify_ssl = True
blueprint = Blueprint('jamf_pro_webhooks', __name__)


@blueprint.route('/webhooks/jamf', methods=['GET'])
@response(template_file='webhooks/jamf/home.html')
def jamf_webhook():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    jamf_pro_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "jamfpro":
            jamf_pro_list.append(each_webhook)

    return {'username': session.get('username'),
            'jamf_list': jamf_pro_list, 'url': session.get('url')}


@blueprint.route('/webhooks/jamf/new', methods=['GET', 'POST'])
def jamf_pro_new():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    if not os.path.isfile(server_json_file):
        return render_template('setup/setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if server_json == []:
        return render_template('setup/setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    if not server_json.get('jawa_address'):
        return redirect(url_for('setup'))
    if not os.path.isfile(webhooks_file):
        data = []
        with open(webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)

    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    if request.method != 'POST':
        return render_template('webhooks/jamf/new.html',
                               webhooks="webhooks",
                               url=session['url'],
                               username=str(escape(session['username'])))
    if not validate_token(session['expires']):
        get_token()
    if request.form.get('webhook_name') != '':
        check = 0
        if ' ' in request.form.get('webhook_name'):
            error_message = "Single-string name only."
            return render_template('error.html',
                                   error_message=error_message,
                                   error="error",
                                   username=str(escape(session['username'])))

        with open(webhooks_file) as json_file:
            data = json.load(json_file)

            x = 0
            id_list = []
            while True:
                try:
                    id_list.append(data[x]['name'])
                    x += 1
                    str_error = None
                except Exception as str_error:
                    if not str_error:
                        continue
                    break
            for id_name in id_list:
                check = 1 if id_name == request.form.get('webhook_name') else 0
        if check != 0:
            error_message = "Name already exists!"
            return render_template('error.html',
                                   error_message=error_message,
                                   error="error",
                                   username=str(escape(session['username'])))

        with open(server_json_file) as json_file:
            data = json.load(json_file)
            server_address = data.get('jawa_address')
            if not server_address:
                return redirect(url_for('setup'))
        if not os.path.isdir(scripts_dir):
            os.mkdir(scripts_dir)
        owd = os.getcwd()
        os.chdir(scripts_dir)

        new_file = request.files.get('new_file')
        if ' ' in new_file.filename:
            new_file.filename = new_file.filename.replace(" ", "-")

        new_file.save(secure_filename(new_file.filename))

        old_script_file = os.path.abspath(
            os.path.join(scripts_dir, f"{new_file.filename}"))
        new_script_file = (os.path.join(scripts_dir,
                                        f"{request.form.get('webhook_name')}-{new_file.filename}"))
        os.rename(old_script_file, new_script_file)

        os.chmod(new_script_file, mode=0o0755)
        os.chdir(owd)
        if request.form.get('event') in [
            'SmartGroupMobileDeviceMembershipChange',
            'SmartGroupComputerMembershipChange',
            'SmartGroupUserMembershipChange'
        ]:

            smart_group_notice = "NOTICE!  This webhook is not yet enabled."
            smart_group_instructions = "Specify desired Smart Group and enable: "
            webhook_enablement = 'false'

        else:
            smart_group_notice = ""
            smart_group_instructions = ""
            webhook_enablement = 'true'

        if request.form.get('event') == "SmartGroupMobileDeviceMembershipChange":
            extra_xml = "<enable_display_fields_for_group_object>true</enable_display_fields_for_group_object>\
                            <display_fields>\
                                <display_field>\
                                    <name>Asset Tag</name>\
                                </display_field>\
                                <display_field>\
                                    <name>Building</name>\
                                </display_field>\
                                <display_field>\
                                    <name>Department</name>\
                                </display_field>\
                                <display_field>\
                                    <name>Email Address</name>\
                                </display_field>\
                                <display_field>\
                                    <name>Last Inventory Update</name>\
                                </display_field>\
                                <display_field>\
                                    <name>Last Enrollment</name>\
                                </display_field>\
                            </display_fields>"
        else:
            extra_xml = ""

        # Check for auth values
        auth_xml = "<authentication_type>NONE</authentication_type>"
        if request.form.get('choice') == 'basic':
            if (
                    request.form.get('username') != '' or
                    request.form.get('password') != ''):
                auth_xml = f"<authentication_type>BASIC</authentication_type>"
                if request.form.get('username') == '':
                    auth_xml += "<username>null</username>"
                else:
                    auth_xml += f"<username>{request.form.get('username')}</username>"
                if request.form.get('password') == '':
                    auth_xml += "<password>null</password>"
                else:
                    auth_xml += f"<password>{request.form.get('password')}</password>"

        data = f"<webhook>" \
               f"<name>{request.form.get('webhook_name')}</name>" \
               f"<enabled>{webhook_enablement}</enabled>" \
               f"<url>{server_address}/hooks/{request.form.get('webhook_name')}</url>" \
               f"<content_type>application/json</content_type>" \
               f"<event>{request.form.get('event')}</event>" \
               f"{auth_xml}" \
               f"{extra_xml}" \
               f"</webhook>"

        full_url = session['url'] + '/JSSResource/webhooks/id/0'
        logthis.info(f"{session.get('username')} creating a new JPS webhook {request.form.get('webhook_name')}.")
        webhook_response = requests.post(full_url,
                                         headers={'Content-Type': 'application/xml',
                                                  "Authorization": f"Bearer {session['token']}",
                                                  'User-Agent': 'JAWA%20v3.0.3'}, data=data,
                                         verify=verify_ssl)
        logthis.info(f"[{webhook_response.status_code}]  {webhook_response.text}")
        if webhook_response.status_code == 409:
            error_message = f"The webhooks name \"{request.form.get('webhook_name')}\" already exists in your Jamf Pro Server."
            return render_template('error.html',
                                   error_message=error_message,
                                   error="error",
                                   username=str(escape(session['username'])))

        result = re.search('<id>(.*)</id>', webhook_response.text)
        jamf_id = result.group(1)
        new_link = "{}/webhooks.html?id={}&o=r".format(session['url'], result.group(1))
        logthis.info(f"{session.get('username')} created a new webhook. "
                     f"Name: {request.form.get('webhook_name')} "
                     f"Jamf link: {new_link}")
        custom_header = ""
        data = json.load(open(webhooks_file))
        if request.form.get('choice') == 'basic':
            webhook_username = request.form.get('username', 'null')
            webhook_password = request.form.get('password', 'null')
        else:
            webhook_username = 'null'
            webhook_password = 'null'
        if request.form.get('choice') == 'custom':
            webhook_apikey = request.form.get('api_key', 'null')
            extra_notice = 'Copy and paste the following into the Header Authentication section of Jamf Pro webhooks:'
            custom_header = {f"x-api-key" :  f"{webhook_apikey}"}
        else:
            webhook_apikey = 'null'
            extra_notice = None

        data.append({"url": str(session['url']),
                     "jawa_admin": str(session['username']),
                     "name": request.form.get('webhook_name'),
                     "webhook_username": webhook_username,
                     "webhook_password": webhook_password,
                     "api_key": webhook_apikey,
                     "event": request.form.get('event'),
                     "script": new_script_file,
                     "description": request.form.get('description'),
                     "tag": "jamfpro",
                     "jamf_id": jamf_id})

        with open(webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)

        new_here = request.form.get('webhook_name')
        success_msg = "New webhook created:"

    return render_template('success.html',
                           webhooks="success",
                           smart_group_instructions=smart_group_instructions,
                           smart_group_notice=smart_group_notice,
                           new_link=new_link,
                           new_here=new_here,
                           success_msg=success_msg, extra_notice=extra_notice,
                           custom_header=custom_header,
                           username=str(escape(session['username'])))


# Edit Existing Webhook
@blueprint.route('/webhooks/jamf/edit', methods=['GET', 'POST'])
@response(template_file='webhooks/jamf/edit.html')
def jamf_pro_edit():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    name = request.args.get('name')
    with open(webhooks_file) as fin:
        webhooks_json = json.load(fin)
    check_for_name = [True for each_webhook in webhooks_json if each_webhook['name'] == name]
    if not check_for_name:
        logthis.info(f"Webhook '{name}' not in json")
        return redirect(url_for('jamf_pro_webhooks.jamf_webhook'))
    webhook_info = [each_webhook for each_webhook in webhooks_json if each_webhook['name'] == name]
    if request.method == 'POST':
        button_choice = request.form.get('button_choice')
        if button_choice == 'Delete':
            return redirect(url_for('webhooks.delete_webhook', target_webhook=name))

        if not validate_token(session['expires']):
            get_token()
        for each_webhook in webhooks_json:
            if each_webhook['name'] == name:
                new_webhook_name = request.form.get('webhook_name')
                if not new_webhook_name:
                    new_webhook_name = name
                description = request.form.get('description')
                new_event = request.form.get('event')
                custom_header = ""
                if request.form.get('choice') == 'basic':
                    webhook_user = request.form.get('username', 'null')
                    webhook_pass = request.form.get('password', 'null')
                else:
                    webhook_user = 'null'
                    webhook_pass = 'null'
                if request.form.get('choice') == 'custom':
                    webhook_apikey = request.form.get('api_key', 'null')
                    extra_notice = 'Copy and paste the following into the Header Authentication section of Jamf Pro webhooks '
                    custom_header = {"x-api-key" : f"{webhook_apikey}"}
                else:
                    webhook_apikey = 'null'
                    extra_notice = None

                if request.files.get('new_file'):
                    new_script = request.files.get('new_file')
                    owd = os.getcwd()
                    os.chdir(scripts_dir)

                    if ' ' in new_script.filename:
                        new_script.filename = new_script.filename.replace(" ", "-")

                    new_filename = f"{new_webhook_name}-{new_script.filename}"
                    new_script.save(secure_filename(new_filename))
                    new_filename = os.path.join(scripts_dir, f"{new_webhook_name}-{new_script.filename}")
                    os.chmod(new_filename, mode=0o0755)
                    os.chdir(owd)
                    each_webhook['script'] = new_filename
                if new_webhook_name:
                    each_webhook['name'] = new_webhook_name
                if description:
                    each_webhook['description'] = description
                if new_event:
                    each_webhook['event'] = new_event
                if webhook_user and webhook_user != "":
                    each_webhook['webhook_username'] = webhook_user
                else:
                    each_webhook['webhook_username'] = 'null'
                if webhook_pass and webhook_pass != "":
                    each_webhook['webhook_password'] = webhook_pass
                else:
                    each_webhook['webhook_password'] = 'null'
                if webhook_apikey and webhook_apikey != "":
                    each_webhook['api_key'] = webhook_apikey
                else:
                    each_webhook['webhook_password'] = 'null'
                each_webhook['jawa_admin'] = session.get('username')
                if each_webhook.get('event') in [
                    'SmartGroupMobileDeviceMembershipChange',
                    'SmartGroupComputerMembershipChange',
                    'SmartGroupUserMembershipChange'
                ]:

                    smart_group_notice = "NOTICE!  This webhook is currently disabled."
                    smart_group_instructions = "Please verify the linked Smart Group and re-enable: "
                    webhook_enablement = 'false'

                else:
                    smart_group_notice = ""
                    smart_group_instructions = ""
                    webhook_enablement = 'true'

                if each_webhook.get('event') == "SmartGroupMobileDeviceMembershipChange":
                    extra_xml = "<enable_display_fields_for_group_object>true</enable_display_fields_for_group_object>\
                                    <display_fields>\
                                        <display_field>\
                                            <name>Asset Tag</name>\
                                        </display_field>\
                                        <display_field>\
                                            <name>Building</name>\
                                        </display_field>\
                                        <display_field>\
                                            <name>Department</name>\
                                        </display_field>\
                                        <display_field>\
                                            <name>Email Address</name>\
                                        </display_field>\
                                        <display_field>\
                                            <name>Last Inventory Update</name>\
                                        </display_field>\
                                        <display_field>\
                                            <name>Last Enrollment</name>\
                                        </display_field>\
                                    </display_fields>"
                else:
                    extra_xml = ""
                    # Check for auth values
                auth_xml = "<authentication_type>NONE</authentication_type>"
                if request.form.get('choice') == 'basic':
                    if (
                            request.form.get('username') != '' or
                            request.form.get('password') != ''):
                        auth_xml = f"<authentication_type>BASIC</authentication_type>"
                        if (request.form.get('username') == 'null' and
                                request.form.get('password') == 'null'):
                            auth_xml = "<authentication_type>NONE</authentication_type>"

                        if request.form.get('username') == '':
                            auth_xml += "<username>null</username>"
                        else:
                            auth_xml += f"<username>{request.form.get('username')}</username>"
                        if request.form.get('password') == '':
                            auth_xml += "<password>null</password>"
                        else:
                            auth_xml += f"<password>{request.form.get('password')}</password>"
                with open(server_json_file) as fin:
                    server_json = json.load(fin)
                server_address = server_json['jawa_address']
                data = f"<webhook>" \
                       f"<name>{each_webhook.get('name')}</name>" \
                       f"<enabled>{webhook_enablement}</enabled>" \
                       f"<url>{server_address}/hooks/{each_webhook.get('name')}</url>" \
                       f"<content_type>application/json</content_type>" \
                       f"<event>{each_webhook.get('event')}</event>" \
                       f"{auth_xml}" \
                       f"{extra_xml}" \
                       f"</webhook>"

                full_url = f"{session['url']}/JSSResource/webhooks/id/{each_webhook.get('jamf_id')}"

                logthis.debug(f"{session.get('username')} editing the JPS webhook {name}.")
                try:
                    webhook_response = requests.put(full_url,
                                                    headers={'Content-Type': 'application/xml',
                                                             "Authorization": f"Bearer {session['token']}",
                                                             'User-Agent': 'JAWA%20v3.0.3'}, data=data,
                                                    verify=verify_ssl)
                except:
                    error_message = f"The request could not be sent to your Jamf Pro server," \
                                    f"check your network connection."
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))
                logthis.debug(f"[{webhook_response.status_code}]  {webhook_response.text}")
                if webhook_response.status_code == 409:
                    error_message = f"The webhooks name \"{name}\" already exists in your Jamf Pro Server."
                    logthis.info(
                        f"[{session.get('url')}] {session.get('username').title()} - error editing webhook. {error_message}")
                    return redirect(url_for('error', error="Duplicate", error_message=error_message,
                                            username=session.get('username')))
                elif webhook_response.status_code == 401:
                    error_message = f"{session.get('username').title()} doesn't have privileges to update webhooks." \
                                    f"Check your account privileges in Jamf Pro Settings"
                    logthis.info(f"[{session.get('url')}] {error_message}")
                    return redirect(url_for('error', error="Insufficient privileges", error_message=error_message,
                                            username=session.get('username')))
                with open(webhooks_file, 'w') as fout:
                    json.dump(webhooks_json, fout, indent=4)
                result = re.search('<id>(.*)</id>', webhook_response.text)
                jamf_id = result.group(1)
                new_link = f"{format(session.get('url'))}/webhooks.html?id={jamf_id}&o=r"
                success_msg = "Webhook edited:"
                logthis.info(f"{session.get('username')} edited a Jamf webhook. "
                             f"Name: {name} "
                             f"Jamf link: {new_link}")
                return {"webhooks": "success", "smart_group_instructions": smart_group_instructions,
                        "smart_group_notice": smart_group_notice,
                        "new_link": new_link,
                        "new_here": new_webhook_name,
                        "success_msg": success_msg, "extra_notice": extra_notice, "custom_header": custom_header,
                        "username": session.get('username'), 'webhook_info': webhook_info, "webhook_name": name,
                        "description": each_webhook.get('description')}

    return {'username': session.get('username'), 'webhook_name': name, 'url': session.get('url'),
            'webhook_info': webhook_info}
