#!/usr/bin/python
# encoding: utf-8
import os
import json
import glob
import time
from collections import defaultdict
from time import sleep
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

from bin.view_modifiers import response

blueprint = Blueprint('okta_webhook', __name__)

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
okta_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'okta_json.json'))
okta_verification_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'okta_verification.py'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@blueprint.route('/webhooks/okta', methods=['GET', 'POST'])
@response(template_file='webhooks/okta/home.html')
def okta_webhook():
    if 'username' not in session:
        return redirect(url_for('logout'))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    okta_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "okta":
            okta_webhooks_list.append(each_webhook)
    print(okta_webhooks_list)

    return {'key': "Have a good weekend my dude.", 'username': session.get('username'),
            'okta_list': okta_webhooks_list}


@blueprint.route('/webhooks/okta/new', methods=['GET', 'POST'])
def okta_new():
    if 'username' not in session:
        return redirect(url_for('logout'))
    os.chmod(okta_verification_file, mode=0o0755)
    # okta_json = '/usr/local/jawa/okta_json.json'

    if not os.path.isfile(webhooks_file):
        data = []
        with open(webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)
    with open(server_json_file) as json_file:
        data = json.load(json_file)
        server_address = data.get('jawa_address')
        if not server_address:
            return redirect(url_for('setup'))
    if request.method != 'POST':
        return render_template('webhooks/okta/new.html', setup="setup",
                               username=str(escape(session['username'])))
    if ' ' in request.form.get('webhookname'):
        error_message = "Single-string name only."
        return render_template('error.html',
                               error_message=error_message,
                               error="error",
                               username=str(escape(session['username'])))


    # if not os.path.isdir('/usr/local/jawa/'):
    #     os.mkdir('/usr/local/jawa/')

    if not os.path.isdir(scripts_dir):
        os.mkdir(scripts_dir)

    okta_server = request.form.get('okta_server')
    okta_token = request.form.get('token')
    okta_name = request.form.get('webhookname')
    okta_event = request.form.get('event')
    description = request.form.get('description')
    webhook_server_url = server_address + '/hooks/' + okta_name
    print(webhook_server_url)
    owd = os.getcwd()
    os.chdir(scripts_dir)

    f = request.files['script']
    if ' ' in f.filename:
        f.filename = f.filename.replace(" ", "-")

    f.save(secure_filename(f.filename))

    old_script_file = os.path.join(scripts_dir, f.filename)

    # hooks_file = '/etc/webhooks.conf'
    data = json.load(open(webhooks_file))

    new_id = okta_name
    script_file = os.path.join(scripts_dir, okta_name + "_" + f.filename)

    os.rename(old_script_file, script_file)
    new_file = script_file

    okta_info = json.load(open(webhooks_file))
    os.chdir(owd)
    for i in data:
        if str(i['name']) == okta_name:
            error_message = "Name already exists!"
            return render_template('error.html',
                                   error_message=error_message,
                                   error="error",
                                   username=str(escape(session['username'])))

    os.chmod(os.path.join(scripts_dir, new_file), mode=0o0755)

    data = {
        "name": okta_name,
        "events": {
            "type": "EVENT_TYPE",
            "items": [okta_event]
        },
        "channel": {
            "type": "HTTP",
            "version": "1.0.0",
            "config": {
                "uri": webhook_server_url,
                "headers": [{
                    "key": "X-Other-Header",
                    "value": "some-other-value"
                }],
                "authScheme": {
                    "type": "HEADER",
                    "key": "Authorization",
                    "value": "${api_key}"
                }
            }
        }
    }

    data = json.dumps(data, indent=4)

    # Makes hook in Okta, gets id
    response = requests.post(okta_server + '/api/v1/eventHooks',
                             headers={
                                 'Accept': 'application/json',
                                 "Authorization": "SSWS {}".format(okta_token),
                                 'Content-Type': 'application/json'},
                             data=data)
    print(response.status_code, response.text)
    response_json = response.json()
    print(response_json)
    okta_id = response_json.get('id')

    okta_info.append({"name": okta_name,
                      "okta_id": okta_id,
                      "okta_event": okta_event,
                      "okta_url": okta_server,
                      "okta_token": okta_token,
                      "script": script_file,
                      "description": description,
                      "webhook_username": "null",
                      "webhook_password": "null",
                      "tag": "okta"})
    if okta_id:
        with open(webhooks_file, 'w') as outfile:
            json.dump(okta_info, outfile, indent=4)

    # Verify/activate
    response = requests.post(okta_server + '/api/v1/eventHooks/{}/lifecycle/verify'.format(okta_id),
                             headers={"Authorization": "SSWS {}".format(okta_token)})

    verification = response.json()
    if 'errorCode' in verification:
        error_message = "Verification failed...try again!"
        return render_template('error.html',
                               error_message=error_message,
                               error="error",
                               username=str(escape(session['username'])))

    return render_template('success.html', username=session.get('username'), login="true")
