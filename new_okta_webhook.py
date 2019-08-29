#!/usr/bin/python
# encoding: utf-8
import os
import json
import glob
import time
from time import sleep
import requests
import re
from werkzeug import secure_filename
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)

new_okta = Blueprint('okta_new', __name__)

@new_okta.route('/okta_new', methods=['GET','POST'])
def okta_new():
	if 'username' in session:	
		os.chmod("/usr/local/jawa/okta_verification.py", 0755)
		okta_json = '/usr/local/jawa/okta_json.json'
		
		if not os.path.isfile('/usr/local/jawa/okta_json.json'):
			data = []
			with open(okta_json, 'w') as outfile:
				json.dump(data, outfile)
		
		if request.method == 'POST':
			if ' ' in request.form.get('webhookname'):
				error_message = "Single-string name only."
				return render_template('error.html', 
					error_message=error_message,
					error="error", 
					username=str(escape(session['username'])))

			with open('/usr/local/jawa/webapp/server.json') as json_file:  
				data = json.load(json_file)
				server_address = data[0]['jawa_address']
			if not os.path.isdir('/usr/local/jawa/'):
				os.mkdir('/usr/local/jawa/')
			if not os.path.isdir('/usr/local/jawa/scripts'):
				os.mkdir('/usr/local/jawa/scripts')
			
			okta_server = request.form.get('okta_server')
			okta_token = request.form.get('token')
			okta_name = request.form.get('webhookname')
			okta_event = request.form.get('event')
			webhook_server_url = server_address + '/hooks/' + okta_name

			os.chdir('/usr/local/jawa/scripts')

			f = request.files['script']
			if ' ' in f.filename:
				f.filename = f.filename.replace(" ", "-")
				
			f.save(secure_filename(f.filename))

			old_script_file = "/usr/local/jawa/scripts/{}".format(f.filename)

			hooks_file = '/etc/webhook.conf'
			data = json.load(open(hooks_file))

			new_id = okta_name
			script_file = "/usr/local/jawa/scripts/{}".format(okta_name + "_" + f.filename)
			
			os.rename(old_script_file, script_file)	
			new_file = script_file

			okta_info = json.load(open(okta_json))

			for i in data:
				if str(i['id']) == okta_name:
					error_message = "Name already exists!"
					return render_template('error.html', 
						error_message=error_message,
						error="error", 
						username=str(escape(session['username'])))

			os.chmod(new_file, 0755)

			data = {
				"name" : okta_name,
				"events" : {
					"type" : "EVENT_TYPE",
					"items" : [okta_event]
					},
				"channel" : {
					"type" : "HTTP",
					"version" : "1.0.0",
					"config" : {
						"uri" : webhook_server_url,
						"headers" : [{
							"key" : "X-Other-Header",
							"value" : "some-other-value"
						}],
						"authScheme" : {
							"type" : "HEADER",
							"key" : "Authorization",
							"value" : "${api_key}"
						}
					}
				}
			}

			data = json.dumps(data)

			# Makes hook in Okta, gets id
			response = requests.post(okta_server + '/api/v1/eventHooks',
				headers={
					'Accept': 'application/json',
					"Authorization": "SSWS {}".format(okta_token),
					'Content-Type': 'application/json'},
				data=data)

			response_json = response.json()

			okta_id = response_json['id']

			okta_info.append({"name": okta_name,
				"okta_id": okta_id,
				"okta_event": okta_event,
				"okta_url": okta_server,
				"okta_token": okta_token,
				"script": script_file})

			with open(okta_json, 'w') as outfile:
				json.dump(okta_info, outfile)

			
			hooks_file = '/etc/webhook.conf'
			data = json.load(open(hooks_file))
			if type(data) is dict:
				data = [data]

			data.append({
				"id": okta_name,
				"execute-command": "/usr/local/jawa/okta_verification.py",
				"response-headers": [{"name": "Content-Type","value": "application/json"}],
				"include-command-output-in-response": True, 
				"command-working-directory": "/",
				"pass-arguments-to-command": [{"source": "entire-payload"}, {"source": "header", "name": "X-Okta-Verification-Challenge"}]})

			with open(hooks_file, 'w') as outfile:
				json.dump(data, outfile)

			sleep(5)

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

			# Make new official hook
			hooks_file = '/etc/webhook.conf'
			data = json.load(open(hooks_file))

			data[:] = [d for d in data if d['id'] != okta_name ]

			with open(hooks_file, 'w') as outfile:
				json.dump(data, outfile)

			if type(data) is dict:
				data = [data]
			
			hooks_file = '/etc/webhook.conf'
			data = json.load(open(hooks_file))
			
			data.append({"id": okta_name,
				"execute-command": new_file,
				"command-working-directory": "/",
				"pass-arguments-to-command":[{"source": "entire-payload"}]})

			with open(hooks_file, 'w') as outfile:
				json.dump(data, outfile)

			return render_template('success.html', login="true")
		
		else:
			return render_template('okta_new.html', setup="setup", username=str(escape(session['username'])))			

	else:
		return render_template('home.html', login="false")