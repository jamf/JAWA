#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep
import re
from crontab import CronTab
from werkzeug import secure_filename
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)

cron_delete = Blueprint('delete_cron', __name__)

@cron_delete.route('/delete_cron', methods=['GET','POST'])
def delete_cron():
	exists = os.path.isfile('/usr/local/jawa/cron.json')
	if exists == False:
		return render_template('cron.html', 
			cron="cron", 
			username=str(escape(session['username'])))
	
	if 'username' in session:
		text = open('/usr/local/jawa/cron.json', 'r+')
		content = text.read()
		webhook_data = json.loads(content)
		i = 0
		names = []
		for item in webhook_data:
			names.append(str(webhook_data[i]['name']))
			i += 1
		
		content = names

		if request.method == 'POST':

			timed_job = request.form.get('timed_job')

			cron_file = '/usr/local/jawa/cron.json'
			data = json.load(open(cron_file))

			for d in data :
				if d['name'] == timed_job:
					scriptPath=(d['script'])
					newScriptPath = scriptPath +  '.old'
					os.rename(scriptPath, newScriptPath)

			cron = CronTab(user='root')
			
			for job in cron:
				if job.comment == timed_job:
					cron.remove(job)

			data[:] = [d for d in data if d.get('name') != timed_job ]

			with open(cron_file, 'w') as outfile:
				json.dump(data, outfile)

			return render_template('success.html', 
				webhooks="success", 
				username=str(escape(session['username'])))
		else:
			return render_template('delete_cron.html', 
				content=content, 
				delete_cron="delete_cron", 
				username=str(escape(session['username'])))
	else:
		return render_template('home.html', 
			login="false")