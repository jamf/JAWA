#!/usr/bin/python
# encoding: utf-8
import sys
import os
import json
import time
from time import sleep
import signal
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

verify_ssl = True

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jp_webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

delete_jp = Blueprint('delete', __name__)


@delete_jp.route('/delete', methods=['GET', 'POST'])
def delete():
    jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jp_webhooks.json'))
    if not os.path.isfile(server_json_file):
        return render_template('setup.html',
                               setup="setup",
                               username=str(escape(session['username'])))

    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('setup.html',
                               setup="setup",
                               jps_url=str(escape(session['url'])),
                               username=str(escape(session['username'])))
    if 'username' in session:
        with open(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jp_webhooks.json')), 'r+') as fin:
            # content = fin.read()
            webhook_data = json.load(fin)
        # text = open(jp_webhooks_file, 'r+')
        # content = text.read()
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

                webhookname = request.form.get('webhookname')
                ts = time.time()

                data = '<webhook>'
                data += '<name>'
                data += '{}.old_{}'.format(webhookname, ts)
                data += '</name><enabled>false</enabled></webhook>'
                full_url = session['url'] + '/JSSResource/webhooks/name/' + webhookname
                response = requests.put(full_url,
                                        auth=(session['username'], session['password']),
                                        headers={'Content-Type': 'application/xml'},
                                        verify=verify_ssl, data=data)

                with open(jp_webhooks_file, "r") as fin:
                    data = json.load(fin)
                # data = json.load(open(jp_webhooks_file))

                for d in data:
                    if d['name'] == webhookname:
                        scriptPath = (d['script'])
                        newScriptPath = scriptPath + '.old'
                        os.rename(scriptPath, newScriptPath)

                data[:] = [d for d in data if d.get('id') != webhookname]

                with open(jp_webhooks_file, 'w') as outfile:
                    json.dump(data, outfile)

                jp_webhooks_file = jp_webhooks_file
                data = json.load(open(jp_webhooks_file))
                data[:] = [d for d in data if d.get('name') != webhookname]

                with open(jp_webhooks_file, 'w') as outfile:
                    json.dump(data, outfile)

            return redirect(url_for('success'))

        else:
            return render_template('delete.html',
                                   text=content, delete="delete",
                                   username=str(escape(session['username'])))
    else:
        return render_template('home.html',
                               login="false")
