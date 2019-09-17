#!/usr/bin/python
# encoding: utf-8
import sys
import os
import json
import base64
import zipfile
import glob
import logging
from time import sleep
from werkzeug import secure_filename
import signal
import requests
import re
from crontab import CronTab
from flask import (Flask, request, render_template, 
	session, redirect, url_for, escape, 
	send_from_directory, Blueprint, abort)


from webapp.new_jp_webhook import new_jp
from webapp.edit_jp_webhook import edit_jp
from webapp.delete_jp_webhook import delete_jp

from webapp.new_okta_webhook import new_okta
from webapp.delete_okta_webhook import delete_okta

from webapp.new_cron_job import new_cron
from webapp.delete_cron_job import cron_delete

# Flask logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.FileHandler('action.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter(
	'%(asctime)s - %(name)s - %(levelname)s - %(message)s')

handler.setFormatter(formatter)
logger.addHandler(handler)
error_message = ""

# Initiate Flask
app = Flask(__name__)

webhook_file = "/etc/webhook.conf"
jp_file = "/usr/local/jawa/jp_webhooks.json"
okta_file = "/usr/local/jawa/okta_json.json"
cron_file = "/usr/local/jawa/cron.json"
server_json_file = '/usr/local/jawa/webapp/server.json'

scripts_directory = "/usr/local/jawa/scripts"

# New Jamf Pro Webhook
app.register_blueprint(new_jp)

# Edit Jamf Pro Webhook
app.register_blueprint(edit_jp)

# Delete Jamf Pro Webhook
app.register_blueprint(delete_jp)

# New Okta Webhook
app.register_blueprint(new_okta)

# Delete Existing Webhook
app.register_blueprint(delete_okta)

# Create a new Cron Job
app.register_blueprint(new_cron)

# Delete a Cron Job
app.register_blueprint(cron_delete)

# Server setup including making .json file necessary for webhooks
@app.route('/setup', methods=['GET','POST'])
def setup():
	if 'username' in session:	
		
		global jawa_address

		data = [{"id": "none",
			"execute-command": "",
			"command-working-directory": "/",
			"pass-arguments-to-command":[{"source": "entire-payload"}]}]
		
		if request.method == 'POST':
			jawa_address = request.form.get('address')
			server_json = [{"jawa_address": jawa_address}]

			with open(server_json_file, "w+") as outfile:
				json.dump(server_json, outfile)

			if not os.path.isfile(webhook_file):
				with open(webhook_file, "w") as outfile:
					json.dump(data, outfile)

			return render_template('success.html', 
				webhooks="success", 
				username=str(escape(session['username'])))
		else:
			return render_template('setup.html', 
				login="false")
	else:
		return render_template('home.html', 
			login="false")


@app.route("/cleanup", methods=['GET', 'POST'])
def cleanup():
	if 'username' in session:
		if request.method == 'POST':

			os.chdir(scripts_directory)
			
			for file in glob.glob("*.old"):
				os.remove(file)

			return render_template('wizard.html', 
				wizard="wizard", 
				username=str(escape(session['username'])))
		
		else:
			return render_template(
				'cleanup.html',
				login="true",
				username=str(escape(session['username'])))
	else:
		return render_template('home.html', 
			login="false")

# Login page verifying communication/permissions to Jamf Pro
@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		session['url'] = request.form['url']
		session['username'] = request.form['username']
		session['password'] = request.form['password']

		jamfurl = session['url']
		logger.info("Logging In: " + str(escape(session['username'])))

		if request.form['password'] != "":
			try:
				response = requests.get(
					session['url'] + '/JSSResource/activationcode', 
					auth=(session['username'], session['password']), 
					headers={'Accept': 'application/json'})

				response.raise_for_status()

			except requests.exceptions.HTTPError as err:
				return render_template('home.html', login="failed")

			response_json = response.json()

			logger.info(
				"Logging In: " + str(escape(session['username'])))

			return redirect(url_for('wizard'))

		else:
			return render_template('home.html', 
				login="failed")

	return render_template('home.html', login="true")


#########################
# General Webapp Settings
#########################

@app.route('/')
def index():
	if 'username' in session:
		return render_template('home.html', 
			username=str(escape(session['username'])), 
			welcome="true")
		
	session.pop('username', None)
	return render_template('home.html', login="true")

@app.route("/")
def home():
	session.pop('username', None)
	return render_template('home.html')

@app.route("/wizard")
def wizard():
	if not os.path.isfile(webhook_file):
		return redirect(url_for('setup'))

	with open(jp_file) as webhook_json:  
		webhooks_installed = json.load(webhook_json)
		webhook_json = []

		response = requests.get(
			session['url'] + '/JSSResource/webhooks',
			auth=(session['username'], session['password']), 
			headers={'Accept': 'application/json'})			

		found_jamf_webhooks = response.json()['webhooks']


		x = 0
		jamf_webhooks = []
		while True:
			try:
				jamf_webhooks.append(found_jamf_webhooks[x]['name'])
				x += 1
				str_error = None
			except Exception as str_error:
				pass
			if str_error:
				sleep(2)
				break
			else:
				continue

		for webhook in webhooks_installed:
			if webhook['name'] in jamf_webhooks:
				webhook_endpoint = '/JSSResource/webhooks/name/'
				response = requests.get(
					session['url'] + webhook_endpoint + webhook['name'], 
					auth=(session['username'], session['password']), 
					headers={'Accept': 'application/json'})

				response_json = response.json()

				jamf_event = response_json['webhook']['event']
				jamf_id = response_json['webhook']['name']

				script = webhook['script'].rsplit('/', 1)
				webhook_json.append({"name": webhook['name'],
					"jamf_id": jamf_id,
					"event": jamf_event,
					"script": script[1],
					"description": webhook['description']})

	data = []

	if not os.path.isfile(cron_file):
		with open(cron_file, "w") as outfile:
			json.dump(data, outfile)	

	with open(cron_file) as cron_json:
		crons_installed = json.load(cron_json)
		crons_json = []
		for cron in crons_installed:
			script = cron['script'].rsplit('/', 1)
			crons_json.append({"name": cron['name'],
				"frequency": cron['frequency'],
				"script": script[1],
				"description": cron['description']})

	data = []

	if not os.path.isfile(okta_file):
		with open(okta_file, "w") as outfile:
			json.dump(data, outfile)	

	with open(okta_file) as okta_json:
		oktas_installed = json.load(okta_json)
		oktas_json = []
		for okta in oktas_installed:
			script = okta['script'].rsplit('/', 1)
			oktas_json.append({"name": okta['name'],
				"event": okta['okta_event'],
				"script": script[1]})

	webhook_url = session['url']

	if webhook_json == []:
		webhook_json = ''
	if crons_json == []:
		crons_json = ''
	if oktas_json == []:
		oktas_json = ''

	if webhook_json == crons_json == oktas_json:
		return redirect(url_for('first_automation'))

	return render_template(
		'wizard.html',
		webhook_url=webhook_url,
		webhooks_installed=webhook_json,
		crons_installed=crons_json,
		oktas_installed=oktas_json,
		login="true",
		username=str(escape(session['username'])))

@app.route("/first_automation")
def first_automation():
	if not os.path.isfile(webhook_file):
		return redirect(url_for('setup'))
		
	if 'username' in session:
		return render_template(
			'first_automation.html',
			login="true",
			username=str(escape(session['username'])))


@app.route("/step_one", methods=['GET', 'POST'])
def step_one():
	if request.method == 'POST':
		if request.form['webhook_source'] == 'jamf':
			return redirect(url_for('webhooks.webhooks'))
			
		if request.form['webhook_source'] == 'okta':
			return redirect(url_for('okta_new.okta_new'))
	
	return render_template(
		'step_one.html',
		login="true",
		username=str(escape(session['username'])))

@app.route("/python")
def python():
	return render_template(
	'python.html',
		login="true",
		username=str(escape(session['username'])))	

@app.route("/bash")
def bash():
	return render_template(
		'bash.html',
		login="true",
		username=str(escape(session['username'])))

@app.route('/success', methods=['GET','POST'])
def success():
	if 'username' in session:
		return render_template(
			'success.html',
			login="true",
			username=str(escape(session['username'])))

@app.route('/error', methods=['GET','POST'])
def error():
	if 'username' in session:
		return render_template('home.html', login="false")

@app.errorhandler(404)
def page_not_found(error):
	if 'username' in session:
		return render_template('home.html', 
			error="true", 
			username=str(escape(session['username']))), 404
	
	return render_template('home.html', 
		error="true", 
		login="true"), 404

@app.route('/logout')
def logout():
	logger.info("Logging Out: " + str(escape(session['username'])))
	session.pop('username', None)

	return redirect(url_for('index'))

if __name__ == '__main__':
	context = (
		'/usr/local/jawa/security/jawa.crt',
		'/usr/local/jawa/security/jawa.key')

	app.secret_key = "*"
	app.run(
		host='0.0.0.0',
		port=443,
		ssl_context=context,
		threaded=True,
		debug=True)
