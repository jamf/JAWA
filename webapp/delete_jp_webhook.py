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

delete_jp = Blueprint('delete', __name__)

@delete_jp.route('/delete', methods=['GET','POST'])
def delete():
	exists = os.path.isfile('/usr/local/jawa/webapp/server.json')
	if exists == False:
		return render_template('setup.html', 
			setup="setup", 
			username=str(escape(session['username'])))
	
	if 'username' in session:
		text = open('/usr/local/jawa/jp_webhooks.json', 'r+')
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

				hooks_file = '/usr/local/jawa/jp_webhooks.json'
				data = json.load(open(hooks_file))
				data[:] = [d for d in data if d.get('name') != webhookname ]

				with open(hooks_file, 'w') as outfile:
					json.dump(data, outfile)				


			return redirect(url_for('success'))

		else:
			return render_template('delete.html', 
				text=content, delete="delete", 
				username=str(escape(session['username'])))
	else:
		return render_template('home.html', 
			login="false")
