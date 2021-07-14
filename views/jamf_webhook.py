import os
import json
import time
from collections import defaultdict
from time import sleep
import signal
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

from bin.load_home import load_home
from bin.view_modifiers import response
from main import jawa_logger

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
verify_ssl = True
blueprint = Blueprint('jamf_pro_webhooks', __name__)


@blueprint.route('/webhooks/jamf', methods=['GET', 'POST'])
@response(template_file='webhooks/jamf/home.html')
def jamf_webhook():
    if 'username' not in session:
        return redirect(url_for('logout'))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    jamf_pro_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "jamfpro":
            jamf_pro_list.append(each_webhook)
    print(jamf_pro_list)

    return {'username': session.get('username'),
            'jamf_list': jamf_pro_list, 'url': session.get('url')}


@blueprint.route('/webhooks/jamf/new', methods=['GET', 'POST'])
def jp_new():
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
    if not os.path.isfile(webhooks_file):
        data = []
        with open(webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)

    if 'username' in session:
        if request.method == 'POST':
            if request.form.get('webhook_name') != '':
                check = 0
                print(check)
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
                            pass
                            if str_error:
                                sleep(2)
                                break
                            else:
                                continue

                    for id_name in id_list:
                        if id_name == request.form.get('webhook_name'):
                            check = 1
                        else:
                            check = 0

                if check != 0:
                    error_message = "Name already exists!"
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                with open(server_json_file) as json_file:
                    data = json.load(json_file)
                    server_address = data['jawa_address']
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
                if (
                        request.form.get('event') == 'SmartGroupMobileDeviceMembershipChange' or
                        request.form.get('event') == 'SmartGroupComputerMembershipChange'):

                    smart_group_notice = "NOTICE!  This webhooks is not yet enabled."
                    smart_group_instructions = "Specify desired Smart Group and enable: "
                    webhook_enablement = 'false'

                else:
                    smart_group_notice = ""
                    smart_group_instructions = ""
                    webhook_enablement = 'true'

                # Check for auth values
                auth_xml = "<authentication_type>NONE</authentication_type>"
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
                       f"</webhook>"

                full_url = session['url'] + '/JSSResource/webhooks/id/0'

                webhook_response = requests.post(full_url,
                                                 auth=(session['username'], session['password']),
                                                 headers={'Content-Type': 'application/xml'}, data=data,
                                                 verify=verify_ssl)
                print(webhook_response.text)
                if webhook_response.status_code == 409:
                    error_message = f"The webhooks name \"{request.form.get('webhook_name')}\" already exists in your Jamf Pro Server."
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                result = re.search('<id>(.*)</id>', webhook_response.text)
                print(result.group(1))
                jamf_id = result.group(1)
                new_link = "{}/webhooks.html?id={}&o=r".format(session['url'], result.group(1))

                data = json.load(open(webhooks_file))
                webhook_username = request.form.get('username')
                webhook_password = request.form.get('password')
                if webhook_username == "":
                    webhook_username = "null"
                if webhook_password == "":
                    webhook_password = "null"

                data.append({"url": str(session['url']),
                             "jawa_admin": str(session['username']),
                             "name": request.form.get('webhook_name'),
                             "webhook_username": webhook_username,
                             "webhook_password": webhook_password,
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
                                   success_msg=success_msg,
                                   username=str(escape(session['username'])))


        else:
            return render_template('webhooks/jamf/new.html',
                                   webhooks="webhooks",
                                   url=session['url'],
                                   # found_mobile_device_groups=found_mobile_device_groups,
                                   # found_computer_groups=found_computer_groups,
                                   username=str(escape(session['username'])))

    else:
        return render_template('home.html', login="false")


# Edit Existing Webhook
@blueprint.route('/webhooks/jamf/edit', methods=['GET', 'POST'])
@response(template_file='webhooks/jamf/edit.html')
def edit():
    if 'username' not in session:
        return redirect(url_for('logout'))
    name = request.args.get('name')
    print(name)
    with open(webhooks_file) as fin:
        webhooks_json = json.load(fin)
    check_for_name = [True for each_webhook in webhooks_json if each_webhook['name'] == name]
    print(check_for_name)
    if not check_for_name:
        jawa_logger().info("name not in json")
        return redirect(url_for('jamf_pro_webhooks.jamf_webhook'))

    if request.method == 'POST':
        # print(name)
        button_choice = request.form.get('button_choice')
        if button_choice == 'Delete':
            return redirect(url_for('webhooks.delete_webhook', target_webhook=name))

        for each_webhook in webhooks_json:
            print(each_webhook)
            if each_webhook['name'] == name:
                new_webhook_name = request.form.get('webhook_name')
                if not new_webhook_name:
                    new_webhook_name = name
                description = request.form.get('description')
                new_event = request.form.get('event')
                webhook_user = request.form.get('username')
                webhook_pass = request.form.get('password')
                print(webhook_user, webhook_pass)
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
                each_webhook['jawa_admin'] = session.get('username')
                if (
                        request.form.get('event') == 'SmartGroupMobileDeviceMembershipChange' or
                        request.form.get('event') == 'SmartGroupComputerMembershipChange'):

                    smart_group_notice = "NOTICE!  This webhooks is not yet enabled."
                    smart_group_instructions = "Specify desired Smart Group and enable: "
                    webhook_enablement = 'false'

                else:
                    smart_group_notice = ""
                    smart_group_instructions = ""
                    webhook_enablement = 'true'

                    # Check for auth values
                auth_xml = "<authentication_type>NONE</authentication_type>"
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
                       f"</webhook>"
                print(data, each_webhook.get('jamf_id'))
                full_url = f"{session['url']}/JSSResource/webhooks/id/{each_webhook.get('jamf_id')}"

                webhook_response = requests.put(full_url,
                                                auth=(session['username'], session['password']),
                                                headers={'Content-Type': 'application/xml'}, data=data,
                                                verify=verify_ssl)
                print(webhook_response.text, webhook_response.status_code)
                if webhook_response.status_code == 409:
                    error_message = f"The webhooks name \"{request.form.get('webhook_name')}\" already exists in your Jamf Pro Server."
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))
                with open(webhooks_file, 'w') as fout:
                    json.dump(webhooks_json, fout, indent=4)
                return redirect(url_for('jamf_pro_webhooks.jamf_webhook'))

    #GET
    webhook_info = [each_webhook for each_webhook in webhooks_json if each_webhook['name'] == name]
    print(webhook_info)
    return {'username': session.get('username'), 'webhook_name': name, 'url': session.get('url'),
            'webhook_info': webhook_info}
