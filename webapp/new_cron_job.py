#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep
import re
from werkzeug import secure_filename
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)

from crontab import CronTab

new_cron = Blueprint('cron', __name__)

@new_cron.route('/cron', methods=['GET','POST'])
def cron():
	global days
	global hours
	global frequencies

	text = open('/usr/local/jawa/time.json', 'r+')
	content = text.read()
	time_data = json.loads(content)
	days_data = time_data['days']
	hours_data = time_data['hours']
	frequencies_data = time_data['frequencies']

	i = 0
	days = []
	for item in days_data:
		days.append(days_data[i])
		i += 1
			
	i = 0
	hours = []
	for item in hours_data:
		hours.append(hours_data[i])
		i += 1
			
	i = 0
	frequencies = []
	for item in frequencies_data:
		frequencies.append(frequencies_data[i])
		i += 1

	if 'username' in session:
		if request.method == 'POST':
			if ' ' in request.form.get('cron_name'):
				error_message = "Single-string name only."
				return render_template('error.html', 
					error_message=error_message,
					error="error", 
					username=str(escape(session['username'])))

			cron_description = request.form.get('cron_description')
			cron_name = request.form.get('cron_name')
			
			if not os.path.isdir('/usr/local/jawa/scripts'):
				os.mkdir('/usr/local/jawa/scripts')
			
			os.chdir('/usr/local/jawa/scripts')
			script = request.files['script']
			if ' ' in script.filename:
				script.filename = script.filename.replace(" ", "-")
				print str(script.filename)
				
			script.save(secure_filename(script.filename))
			script_file = "/usr/local/jawa/scripts/{}".format(script.filename)

			os.chmod(script_file, 0755)

			frequency = request.form.get('frequency')

			cron_json = '/usr/local/jawa/cron.json'
			
			if not os.path.isfile('/usr/local/jawa/cron.json'):
				data = []
				with open(cron_json, 'w') as outfile:
					json.dump(data, outfile)
			
			data = json.load(open(cron_json))

			for i in data:
				print i
				print " ~ ~ ~ ~ ~"
				if str(i['name']) == cron_name:
					error_message = "Name already exists!"
					return render_template('error.html', 
						error_message=error_message,
						error="error", 
						username=str(escape(session['username'])))

			data.append({"name": cron_name,
				"description": cron_description,
				"frequency": frequency,
				"script": script_file})

			with open(cron_json, 'w') as outfile:
				json.dump(data, outfile)
			
			cron = CronTab(user='root')

			if frequency == "everyhour":
				job1 = cron.new(command=script_file, comment=cron_name)
				job1.every().hours()
				job1.minute.on(0)
				cron.write()


			if frequency == "everyday":
				time = request.form.get('daytime')
				job1 = cron.new(command=script_file, comment=cron_name)
				job1.day.every(1)
				job1.hour.on(time)
				job1.minute.on(0)
				cron.write()

			if frequency == "everyweek":
				day = request.form.get('weekday')
				time = request.form.get('weektime')
				job1 = cron.new(command=script_file, comment=cron_name)
				job1.dow.on(day)
				job1.hour.on(time)
				job1.minute.on(0)
				cron.write()

			if frequency == "everymonth":
				day = request.form.get('monthday')
				time = request.form.get('monthtime')
				job1 = cron.new(command=script_file, comment=cron_name)
				job1.day.on(day)
				job1.hour.on(time)
				job1.minute.on(0)
				cron.write()

			return render_template('success.html', 
				webhooks="success", 
				username=str(escape(session['username'])))

		else:
			return render_template('cron.html', 
				cron="cron",
				frequencies=frequencies,
				days=days,
				hours=hours,
				username=str(escape(session['username'])))

	else:
		return render_template('home.html', 
			login="false")
