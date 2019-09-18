#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep, time
import requests
import re
from werkzeug import secure_filename
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)

edit_jp = Blueprint('edit', __name__)

# Edit Existing Webhook
@edit_jp.route('/edit', methods=['GET','POST'])
def edit():
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

				check = 0
				
				with open('/etc/webhook.conf') as json_file:  
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

				with open('/usr/local/jawa/webapp/server.json') as json_file:  
					data = json.load(json_file)
					server_address = data[0]['jawa_address']

				if not os.path.isdir('/usr/local/jawa/'):
					os.mkdir('/usr/local/jawa/')

				if not os.path.isdir('/usr/local/jawa/scripts'):
					os.mkdir('/usr/local/jawa/scripts')

				os.chdir('/usr/local/jawa/scripts')

				f = request.files['script']
				if ' ' in f.filename:
					f.filename = f.filename.replace(" ", "-")

				f.save(secure_filename(f.filename))

				script_file = "/usr/local/jawa/scripts/{}".format(f.filename)
				hooks_file = '/etc/webhook.conf'

				os.chmod(script_file, 0755)
				
				with open(hooks_file) as json_file:  
					data = json.load(json_file)
					
					for x in data:
						if request.form.get('webhookname') in x['id']:
							x['execute-command'] = str(script_file)
							if request.form.get('new_webhookname') != '':
								x['id'] = str(request.form.get('new_webhookname'))
					
					with open(hooks_file, 'w') as outfile:
						json.dump(data, outfile)	

				jp_hooks_file = '/usr/local/jawa/jp_webhooks.json'

				with open(jp_hooks_file) as json_file:  
					data = json.load(json_file)
					
					for x in data:
						if request.form.get('webhookname') in x['name']:
							x['script'] = str(script_file)
							if request.form.get('new_webhookname') != '':
								x['name'] = str(request.form.get('new_webhookname'))
					
					with open(jp_hooks_file, 'w') as outfile:
						json.dump(data, outfile)					
				

				webhookname = request.form.get('webhookname')

				new_webhookname = webhookname
				with open('/usr/local/jawa/webapp/server.json') as json_file:
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

						smart_group_notice = "NOTICE!  This webhooks is not yet enabled."
						smart_group_instructions = "Specify desired Smart Group and enable: "
						webhook_enablement = 'false'
					
					else:
						smart_group_instructions = ""
						webhook_enablement = 'true'

				if add_name == '' and add_event == '':
					print "No Jamf Change Needed"
				
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
						data=data)


			return render_template('success.html', 
				webhooks="success", 
				username=str(escape(session['username'])))

		else:
			return render_template('edit.html', 
				text=content, 
				edit="edit", 
				username=str(escape(session['username'])))

	else:
		return render_template('home.html', 
			login="false")
