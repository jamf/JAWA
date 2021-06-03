#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep
import signal
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

webhook_conf = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhook.conf'))
server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jp_webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
print(server_json_file, jp_webhooks_file)
verify_ssl = True
new_jp = Blueprint('webhooks', __name__)


@new_jp.route('/webhooks', methods=['GET', 'POST'])
def webhooks():
    if not os.path.isfile(server_json_file):
        return render_template('setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if server_json == []:
        return render_template('setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    if not os.path.isfile(jp_webhooks_file):
        data = []
        with open(jp_webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)

    if 'username' in session:

        # response = requests.get(session['url'] + '/JSSResource/computergroups',
        # 	auth=(session['username'], session['password']),
        # 	headers={'Accept': 'application/json'})

        # response_json = response.json()

        # computer_groups = response_json['computer_groups']
        # found_computer_groups = []
        # for computer_group in computer_groups:
        # 	if computer_group['is_smart'] is True:
        # 		found_computer_groups.append(computer_group)

        # print found_computer_groups

        # response = requests.get(session['url'] + '/JSSResource/mobiledevicegroups',
        # 	auth=(session['username'], session['password']),
        # 	headers={'Accept': 'application/json'})

        # response_json = response.json()

        # mobile_device_groups = response_json['mobile_device_groups']
        # found_mobile_device_groups = []
        # for mobile_device_group in mobile_device_groups:
        # 	if mobile_device_group['is_smart'] is True:
        # 		found_mobile_device_groups.append(mobile_device_group)

        # print found_mobile_device_groups

        if request.method == 'POST':
            if request.form.get('webhookname') != '':
                check = 0
                if ' ' in request.form.get('webhookname'):
                    error_message = "Single-string name only."
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                with open(webhook_conf) as json_file:
                    data = json.load(json_file)

                    x = 0
                    id_list = []
                    while True:
                        try:
                            id_list.append(data[x]['id'])
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
                        if id_name == request.form.get('webhookname'):
                            check = 1
                        else:
                            check = 0

                if check is not 0:
                    error_message = "Name already exists!"
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                with open(server_json_file) as json_file:
                    data = json.load(json_file)
                    server_address = data['jawa_address']

                # if not os.path.isdir('/usr/local/jawa/'):
                #     os.mkdir('/usr/local/jawa/')
                if not os.path.isdir(scripts_dir):
                    os.mkdir(scripts_dir)

                os.chdir(scripts_dir)

                f = request.files['script']
                if ' ' in f.filename:
                    f.filename = f.filename.replace(" ", "-")

                f.save(secure_filename(f.filename))

                old_script_file = os.path.abspath(
                    os.path.join(scripts_dir, f"{f.filename}"))
                new_script_file = (os.path.join(scripts_dir,
                                                f"{request.form.get('webhookname')}-{f.filename}"))
                os.rename(old_script_file, new_script_file)
                hooks_file = (os.path.join(os.path.join(os.path.dirname(__file__), "..", "data"), "webhook.conf"))

                if not os.path.exists(hooks_file):
                    with open(hooks_file, "w") as fout:
                        fout.write("[]")
                data = json.load(open(hooks_file))

                new_id = request.form.get('new_webhookname')

                os.chmod(new_script_file, mode=0o0755)

                if type(data) is dict:
                    data = [data]

                data.append({"id": request.form.get('webhookname'),
                             "execute-command": new_script_file,
                             "command-working-directory": "/",
                             "pass-arguments-to-command": [{"source": "entire-payload"}]})

                # with open(hooks_file, 'w') as outfile:
                #     json.dump(data, outfile)

                # hooks_file = '/etc/webhook.conf'
                data = json.load(open(hooks_file))

                data[:] = [d for d in data if d.get('id') != 'none']

                with open(hooks_file, 'w') as outfile:
                    json.dump(data, outfile, indent=4)

                if (
                        request.form.get('event') == 'SmartGroupMobileDeviceMembershipChange' or
                        request.form.get('event') == 'SmartGroupComputerMembershipChange'):

                    smart_group_notice = "NOTICE!  This webhook is not yet enabled."
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
                        request.form.get('password') != '' ):
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
                       f"<name>{request.form.get('webhookname')}</name>" \
                       f"<enabled>{webhook_enablement}</enabled>" \
                       f"<url>{server_json['jawa_address']}/hooks/{request.form.get('webhookname')}</url>" \
                       f"<content_type>application/json</content_type>" \
                       f"<event>{request.form.get('event')}</event>" \
                       f"{auth_xml}" \
                       f"</webhook>"

                full_url = session['url'] + '/JSSResource/webhooks/id/0'

                response = requests.post(full_url,
                                         auth=(session['username'], session['password']),
                                         headers={'Content-Type': 'application/xml'}, data=data,
                                         verify=verify_ssl)


                result = re.search('<id>(.*)</id>', response.text)
                new_link = "{}/webhooks.html?id={}".format(session['url'], result.group(1))

                data = json.load(open(jp_webhooks_file))

                data.append({"url": str(session['url']),
                             "jawa_admin": str(session['username']),
                             "name": request.form.get('webhookname'),
                             "webhook_username": request.form.get('username'),
                             "webhook_password": request.form.get('password'),
                             "event": request.form.get('event'),
                             "script": new_script_file,
                             "description": request.form.get('description')})

                with open(jp_webhooks_file, 'w') as outfile:
                    json.dump(data, outfile, indent=4)

                new_here = "Link"
                new_webhook = "New webhook created."

            return render_template('success.html',
                                   webhooks="success",
                                   smart_group_instructions=smart_group_instructions,
                                   smart_group_notice=smart_group_notice,
                                   new_link=new_link,
                                   new_here=new_here,
                                   new_webhook=new_webhook,
                                   username=str(escape(session['username'])))


        else:
            return render_template('webhooks.html',
                                   webhooks="webhooks",
                                   url=session['url'],
                                   # found_mobile_device_groups=found_mobile_device_groups,
                                   # found_computer_groups=found_computer_groups,
                                   username=str(escape(session['username'])))

    else:
        return render_template('home.html', login="false")
