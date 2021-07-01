#!/usr/bin/python3

from collections import defaultdict
import os
import json
import time
import requests
from flask import (request, render_template,
                   session, redirect, url_for, escape,
                   Blueprint)

delete_okta = Blueprint('okta_delete', __name__)

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
webhooks_json = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@delete_okta.route('/okta_delete', methods=['GET', 'POST'])
def okta_delete():
    exists = os.path.isfile(server_json_file)
    if exists == False:
        return render_template('setup.html',
                               setup="setup",
                               username=str(escape(session['username'])))

    if 'username' in session:
        with open(webhooks_json, 'r+') as fin:
            content = fin.read()
        webhook_data = json.loads(content)
        i = 0
        names = []
        for item in webhook_data:
            data = defaultdict(lambda: "MISSING", item)
            tag = item['tag']
            if tag == "okta":
                names.append(str(webhook_data[i]['name']))
            i += 1

        content = names

        if request.method == 'POST':
            if request.form.get('webhookname') != '':

                webhookname = request.form.get('webhookname')
                ts = time.time()


                data = json.load(open(webhooks_json))

                for d in data:
                    if d['id'] == webhookname:
                        scriptPath = (d['execute-command'])
                        newScriptPath = scriptPath + '.old'
                        os.rename(scriptPath, newScriptPath)

                data[:] = [d for d in data if d.get('id') != webhookname]

                with open(webhooks_json, 'w') as outfile:
                    json.dump(data, outfile)


                data = json.load(open(webhooks_json))

                for d in data:
                    if d['name'] == webhookname:
                        response = requests.post(
                            d['okta_url'] + '/api/v1/eventHooks/{}/lifecycle/deactivate'.format(d['okta_id']),
                            headers={"Authorization": "SSWS {}".format(d['okta_token'])})

                        response = requests.delete(d['okta_url'] + '/api/v1/eventHooks/{}'.format(d['okta_id']),
                                                   headers={"Authorization": "SSWS {}".format(d['okta_token'])})

                data[:] = [d for d in data if d.get('name') != webhookname]

                with open(webhooks_json, 'w') as outfile:
                    json.dump(data, outfile)

            return redirect(url_for('success'))

        else:
            return render_template('okta_delete.html',
                                   text=content, delete="delete",
                                   username=str(escape(session['username'])))
    else:
        return render_template('home.html',
                               login="false")
