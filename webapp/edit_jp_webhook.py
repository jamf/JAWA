#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep, time
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jp_webhooks.json'))
webhook_conf = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhook.conf'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

edit_jp = Blueprint('edit', __name__)
verify_ssl = True


# Edit Existing Webhook
@edit_jp.route('/edit', methods=['GET', 'POST'])
def edit():
    if not os.path.isfile(server_json_file):
        return render_template('setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    if 'username' in session:
        with open(jp_webhooks_file, 'r+') as text:
            content = text.read()
            webhook_data = json.loads(content)

        i = 0
        names = []
        for item in webhook_data:
            names.append(str(webhook_data[i]['name']))
            i += 1

        content = names

        if request.method == 'POST':
            if request.form.get('webhookname') != '':
                if ' ' in request.form.get('webhookname'):
                    error_message = "Single-string name only."
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                check = 0

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
                        if id_name == request.form.get('new_webhookname'):
                            check = 1
                        else:
                            check = 0

                if check == 1:
                    error_message = "Name already exists!"
                    return render_template('error.html',
                                           error_message=error_message,
                                           error="error",
                                           username=str(escape(session['username'])))

                with open(server_json_file) as json_file:
                    data = json.load(json_file)
                    server_address = data[0]['jawa_address']

                if not os.path.isdir(scripts_dir):
                    os.mkdir(scripts_dir)
                os.chdir(scripts_dir)

                f = request.files['script']
                if ' ' in f.filename:
                    f.filename = f.filename.replace(" ", "-")

                f.save(secure_filename(f.filename))
                old_script_file = os.path.join(scripts_dir, f.filename)
                if request.form.get('new_webhookname') == '':
                    new_script_file = os.path.join(scripts_dir, f"{request.form.get('webhookname')}-{f.filename}")
                else:
                    new_script_file = os.path.join(scripts_dir, f"{request.form.get('new_webhookname')}-{f.filename}")

                os.rename(old_script_file, new_script_file)
                script_file = new_script_file
                # webhook_conf = webhook_conf

                os.chmod(script_file, mode=0o0755)

                with open(webhook_conf) as json_file:
                    data = json.load(json_file)

                    for x in data:
                        if request.form.get('webhookname') in x['id']:
                            x['execute-command'] = str(script_file)
                            if request.form.get('new_webhookname') != '':
                                x['id'] = str(request.form.get('new_webhookname'))
                            x['event'] = str(request.form.get('event'))
                            # if request.form.get('event') != '':
                            #     pass

                    with open(webhook_conf, 'w') as outfile:
                        json.dump(data, outfile, indent=4)

                with open(jp_webhooks_file) as json_file:
                    data = json.load(json_file)

                    for x in data:
                        if request.form.get('webhookname') in x['name']:
                            x['script'] = str(script_file)
                            x['event'] = str(request.form.get('event'))
                            if request.form.get('new_webhookname') != '':
                                x['name'] = str(request.form.get('new_webhookname'))

                    with open(jp_webhooks_file, 'w') as outfile:
                        json.dump(data, outfile, indent=4)

                webhookname = request.form.get('webhookname')

                new_webhookname = webhookname
                with open(server_json_file) as json_file:
                    data = json.load(json_file)
                    server_address = data[0]['jawa_address']

                add_name = ''
                if request.form.get('new_webhookname') != "":
                    new_webhookname = request.form.get('new_webhookname')
                    add_name = '<name>{}</name>'.format(new_webhookname)
                    add_name += '<url>{}/hooks/{}</url>'.format(
                        server_address, new_webhookname)

                add_event = ''
                if request.form.get('event') != 'unchanged':
                    new_event = request.form.get('event')
                    add_event = '<event>{}</event>'.format(new_event)

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

                else:
                    smart_group_notice = ""
                    smart_group_instructions = ""
                    webhook_enablement = 'true'

                if add_name == '' and add_event == '':
                    print("No Jamf Change Needed")
                    smart_group_instructions = ""
                    smart_group_notice = ""
                    new_link = ""
                    new_here = ""

                else:
                    data = '<webhook>'
                    data += add_name
                    data += '<enabled>' + webhook_enablement + '</enabled>'
                    data += add_event
                    data += '</webhook>'
                    full_url = session['url'] + '/JSSResource/webhooks/name/' + webhookname
                    response = requests.put(full_url,
                                            auth=(session['username'], session['password']),
                                            headers={'Content-Type': 'application/xml'},
                                            verify=verify_ssl,
                                            data=data)
                    result = re.search('<id>(.*)</id>', response.text)
                    new_link = "{}/webhooks.html?id={}".format(session['url'], result.group(1))
                    new_here = "Link"

            return render_template('success.html',
                                   webhooks="success",
                                   smart_group_instructions=smart_group_instructions,
                                   smart_group_notice=smart_group_notice,
                                   new_link=new_link,
                                   new_here=new_here,
                                   username=str(escape(session['username'])))

        else:
            return render_template('edit.html',
                                   text=content,
                                   edit="edit",
                                   username=str(escape(session['username'])))

    else:
        return render_template('home.html',
                               login="false")
