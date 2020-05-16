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
verify_ssl = True
new_jp = Blueprint('webhooks', __name__)

@new_jp.route('/webhooks', methods=['GET','POST'])
def webhooks():
	exists = os.path.isfile('/usr/local/jawa/webapp/server.json')
	if exists == False:
		return render_template('setup.html', 
			setup="setup",
			jps_url=str(escape(session['url'])),
			username=str(escape(session['username'])))
	exists = os.path.isfile('/usr/local/jawa/jpwebhooks.json')	
	if exists == False:
		data = []
		with open('/usr/local/jawa/jpwebhooks.json', 'w') as outfile:
			json.dump(data, outfile)		
	
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
				
				old_script_file = "/usr/local/jawa/scripts/{}".format(f.filename)
				new_script_file = "/usr/local/jawa/scripts/{}-{}".format(request.form.get('webhookname'), f.filename)
				os.rename(old_script_file, new_script_file)
				hooks_file = '/etc/webhook.conf'
				jp_hooks = '/usr/local/jawa/jp_webhooks.json'
				data = json.load(open(hooks_file))

				new_id = request.form.get('new_webhookname')

				os.chmod(new_script_file, mode=0o0755)

				if type(data) is dict:
					data = [data]

				data.append({"id": request.form.get('webhookname'),
					"execute-command": new_script_file,
					"command-working-directory": "/",
					"pass-arguments-to-command":[{"source": "entire-payload"}]})

				with open(hooks_file, 'w') as outfile:
					json.dump(data, outfile)

				hooks_file = '/etc/webhook.conf'
				data = json.load(open(hooks_file))

				data[:] = [d for d in data if d.get('id') != 'none' ]

				with open(hooks_file, 'w') as outfile:
					json.dump(data, outfile)
				
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
				data = '<webhook>'
				data += '<name>'
				data += request.form.get('webhookname')
				data += '</name><enabled>' + webhook_enablement + '</enabled><url>'
				data += "{}/hooks/{}".format(server_address, request.form.get('webhookname'))
				data += '</url><content_type>application/json</content_type>'
				data += '<event>{}</event>'.format(request.form.get('event'))
				data += '</webhook>'
				full_url = session['url'] + '/JSSResource/webhooks/id/0'

				response = requests.post(full_url, 
					auth=(session['username'], session['password']), 
					headers={'Content-Type': 'application/xml'}, data=data,
					verify=verify_ssl)

				result = re.search('<id>(.*)</id>', response.text)
				new_link = "{}/webhooks.html?id={}".format(session['url'],result.group(1))

				data = json.load(open('/usr/local/jawa/jp_webhooks.json'))

				data.append({"url": str(session['url']),
					"username": str(session['username']),
					"name": request.form.get('webhookname'),
					"event": request.form.get('event'),
					"script": new_script_file,
					"description": request.form.get('description')})

				with open('/usr/local/jawa/jp_webhooks.json', 'w') as outfile:
					json.dump(data, outfile)	

				

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
