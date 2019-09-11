#!/usr/bin/python
# encoding: utf-8
import os
import json
import time
from time import sleep
import requests
import re
from werkzeug import secure_filename
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)

delete_okta = Blueprint('okta_delete', __name__)

@delete_okta.route('/okta_delete', methods=['GET','POST'])
def okta_delete():
	exists = os.path.isfile('/usr/local/jawa/webapp/server.json')
	if exists == False:
		return render_template('setup.html', 
			setup="setup", 
			username=str(escape(session['username'])))
	
	if 'username' in session:
		text = open('/usr/local/jawa/okta_json.json', 'r+')
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

				webhookname = request.form.get('webhookname')
				ts = time.time()

				hooks_file = '/etc/webhook.conf'
				data = json.load(open(hooks_file))


				for d in data :
					if d['id'] == webhookname:
						scriptPath=(d['execute-command'])
						newScriptPath = scriptPath +  '.old'
						os.rename(scriptPath, newScriptPath)

				data[:] = [d for d in data if d.get('id') != webhookname ]

				with open(hooks_file, 'w') as outfile:
					json.dump(data, outfile)

				hooks_file = '/usr/local/jawa/okta_json.json'
				data = json.load(open(hooks_file))

				for d in data :
					if d['name'] == webhookname:
						response = requests.post(d['okta_url'] + '/api/v1/eventHooks/{}/lifecycle/deactivate'.format(d['okta_id']),
							headers={"Authorization": "SSWS {}".format(d['okta_token'])})

						response = requests.delete(d['okta_url'] + '/api/v1/eventHooks/{}'.format(d['okta_id']),
							headers={"Authorization": "SSWS {}".format(d['okta_token'])})


				data[:] = [d for d in data if d.get('name') != webhookname ]

				with open(hooks_file, 'w') as outfile:
					json.dump(data, outfile)


			return redirect(url_for('success'))

		else:
			return render_template('okta_delete.html', 
				text=content, delete="delete", 
				username=str(escape(session['username'])))
	else:
		return render_template('home.html', 
			login="false")

