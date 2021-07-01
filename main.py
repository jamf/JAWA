#!/usr/bin/python3
# encoding: utf-8
from collections import defaultdict
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape)
import glob
import json
import logging
import os
import requests
from waitress import serve



def jawa_logger():
    global logger
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'jawa.log'))
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('waitress')
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if (logger.hasHandlers()):
        logger.handlers.clear()
    logger.addHandler(handler)
    return logger


# Flask logging
jawa_logger()
error_message = ""
verify_ssl = True  # Enables Jamf Pro SSL certificate verification

# Initiate Flask
app = Flask(__name__)


def main():
    base_dir = os.path.dirname(__file__)
    jawa_logger().info(f"JAWA initializing...\n Sandcrawler home:  {base_dir}")
    environment_setup(base_dir)
    register_blueprints()
    app.secret_key = "untini"
    serve(app, url_scheme='https', host='0.0.0.0', port=8000)


def environment_setup(project_dir):
    global jp_file, cron_file, server_json_file, scripts_directory
    jp_file = os.path.join(project_dir, 'data', 'webhooks.json')
    cron_file = os.path.join(project_dir, 'data', 'cron.json')
    server_json_file = os.path.join(project_dir, 'data', 'server.json')
    scripts_directory = os.path.join(project_dir, 'scripts')
    jawa_logger().info(f"Detecting JAWA environment:\n"
                       f"Webhooks configuration file: {jp_file}\n"
                       f"Cron configuration file: {cron_file}\n"
                       f"Server configuration file: {server_json_file}\n"
                       f"Scripts directory: {scripts_directory}")


def register_blueprints():
    # JAWA Receiver
    from webhook import jawa_receiver
    app.register_blueprint(jawa_receiver.blueprint)
    # New Jamf Pro Webhook
    from views.new_jp_webhook import new_jp
    app.register_blueprint(new_jp)
    # Edit Jamf Pro Webhook
    from views.edit_jp_webhook import edit_jp
    app.register_blueprint(edit_jp)
    # Delete Jamf Pro Webhook
    from views.delete_jp_webhook import delete_jp
    app.register_blueprint(delete_jp)
    # New Okta Webhook
    from views.new_okta_webhook import new_okta
    app.register_blueprint(new_okta)
    # Delete Existing Webhook
    from views.delete_okta_webhook import delete_okta
    app.register_blueprint(delete_okta)
    # Create a new Cron Job
    from views.new_cron_job import new_cron
    app.register_blueprint(new_cron)
    # Delete a Cron Job
    from views.delete_cron_job import cron_delete
    app.register_blueprint(cron_delete)
    # Log view
    from views import log_view
    app.register_blueprint(log_view.blueprint)
    # Resources (aka files) view
    from views import resource_view
    app.register_blueprint(resource_view.blueprint)

# Server setup including making .json file necessary for webhooks


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if 'username' in session:
        if request.method == 'POST':
            jawa_logger().info(f"{session.get('username')} - /setup - POST")
            server_url = request.form.get('address')
            jps_url = request.form.get('jss-lock')
            jps2_check = request.form.get('alternate-jps')
            jps_url2 = request.form.get('alternate')
            jawa_logger().info(f"{session.get('username')} made JAWA Setup Changes\n"
                               f"JAWA URL: {server_url}\n"
                               f"Primary JPS: {jps_url}\n"
                               f"Alternate JPS: {jps_url2}\n"
                               f"Alternate enabled?: {jps2_check}")
            new_json = {}
            if server_url != '':
                new_json['jawa_address'] = server_url
            # print(server_url)
            if jps_url != '':
                new_json['jps_url'] = jps_url
            # print(new_json)
            if not os.path.isfile(server_json_file):
                with open(server_json_file, "w") as outfile:
                    server_json = {'jawa_address': server_url, 'jps_url': jps_url, 'alternate_jps': jps_url2}
                    json.dump(server_json, outfile)
            elif os.path.isfile(server_json_file):
                with open(server_json_file, "w") as outfile:
                    server_json = {'jawa_address': server_url, 'jps_url': jps_url, 'alternate_jps': jps_url2}
                    json.dump(server_json, outfile)
                with open(server_json_file, "r") as fin:
                    data = json.load(fin)
                data.update(new_json)
                with open(server_json_file, "w+") as outfile:
                    json.dump(data, outfile)

            return render_template('success.html',
                                   webhooks="success",
                                   username=str(escape(session['username'])))
        else:
            jawa_logger().info(f"{session.get('username')} - /setup - GET")
            if not os.path.isfile(server_json_file):
                with open(server_json_file, "w") as outfile:
                    server_json = {'jawa_address': '', 'jps_url': '', 'alternate_jps': ''}
                    json.dump(server_json, outfile)
            with open(server_json_file, "r") as fin:
                server_json = json.load(fin)
            jps_url2 = server_json['alternate_jps']
            if jps_url2 == str(escape(session['url'])):
                primary_jps = server_json['jps_url']
            else:
                primary_jps = str(escape(session['url']))
            jawa_url = server_json['jawa_address']
            return render_template('setup.html',
                                   login="false", jps_url=primary_jps, jps_url2=jps_url2,
                                   jawa_url=jawa_url)
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


#########################
# General Webapp Settings
#########################

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if os.path.isfile(server_json_file):
            with open(server_json_file) as json_file:
                server_json = json.load(json_file)
            if request.form['active_url'] != '':
                session['url'] = str(request.form.get('active_url'))
            else:
                if server_json.get('jps_url', 0):
                    if server_json['jps_url'] is not None and len(server_json['jps_url']) != 0:
                        session['url'] = str(server_json['jps_url'])
                else:
                    session['url'] = request.form['url']
        else:
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
                    headers={'Accept': 'application/json'},
                    verify=verify_ssl)

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


@app.route('/')
@app.route('/home.html')
def index():
    return load_home()


def load_home():
    if not os.path.isfile(server_json_file):
        return render_template('home.html')
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    else:
        with open(server_json_file) as json_file:
            server_json = json.load(json_file)
        # print(server_json)

        if not 'jps_url' in server_json:
            return render_template('home.html')
        elif server_json['jps_url'] == None:
            return render_template('home.html')
        elif len(server_json['jps_url']) == 0:
            return render_template('home.html')
        else:
            if not 'alternate_jps' in server_json:
                return render_template('home.html')

            if server_json['alternate_jps'] != "":
                return render_template('home.html',
                                       jps_url=server_json['jps_url'],
                                       jps_url2=server_json['alternate_jps'],
                                       welcome="true", jsslock="true")

            session['url'] = server_json['jps_url']
            return render_template('home.html',
                                   jps_url=str(escape(session['url'])),
                                   welcome="true", jsslock="true")
    session.pop('username', None)
    return render_template('home.html', login="true")


@app.route("/")
def home():
    if 'username' in session:
        if not os.path.isfile(server_json_file):
            return render_template('home.html')
        else:
            with open(server_json_file) as json_file:
                server_json = json.load(json_file)
            # print(server_json)
            if not 'jps_url' in server_json:
                return render_template('home.html')
            elif server_json['jps_url'] is None:
                return render_template('home.html')
            elif len(server_json['jps_url']) == 0:
                return render_template('home.html')
            else:
                session['url'] = server_json['jps_url']
                return render_template('home.html',
                                       jps_url=str(escape(session['url'])),
                                       welcome="true", jsslock="true")

    session.pop('username', None)
    return render_template('home.html')


@app.route("/wizard")
def wizard():
    with open(jp_file) as webhook_json:
        webhooks_installed = json.load(webhook_json)
    jamf_pro_webhooks = []
    okta_webhooks = []
    for each_webhook in webhooks_installed:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "jamfpro":
            jamf_pro_webhooks.append(each_webhook)
        elif tag == "okta":
            okta_webhooks.append(each_webhook)

    # print(f"Full JP Webhook list: {jamf_pro_webhooks}")

    response = requests.get(
        session['url'] + '/JSSResource/webhooks',
        auth=(session['username'], session['password']),
        headers={'Accept': 'application/json'},
        verify=verify_ssl)

    found_jamf_webhooks = response.json()['webhooks']

    jamf_webhooks = []

    x = 0
    while True:
        try:
            jamf_webhooks.append(found_jamf_webhooks[x]['name'])
            x += 1
            str_error = None
        except Exception as str_error:
            pass
            if str_error:
                # sleep(2)
                break
            else:
                continue

    for webhook in webhooks_installed:
        if webhook['name'] in jamf_webhooks:
            webhook_endpoint = '/JSSResource/webhooks/name/'
            response = requests.get(
                session['url'] + webhook_endpoint + webhook['name'],
                auth=(session['username'], session['password']),
                headers={'Accept': 'application/json'},
                verify=verify_ssl)

            response_json = response.json()

            jamf_event = response_json['webhook']['event']
            jamf_id = response_json['webhook']['id']
            script = webhook['script']

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

    webhook_url = session['url']

    if not webhook_json:
        webhook_json = ''
    if not crons_json:
        crons_json = ''
    # if not oktas_json:
    #     oktas_json = ''

    if webhook_json == crons_json:
        return redirect(url_for('first_automation'))
    return render_template(
        'wizard.html',
        webhook_url=webhook_url,
        webhooks_installed=jamf_pro_webhooks,
        crons_installed=crons_json,
        oktas_installed=okta_webhooks,
        login="true",
        username=str(escape(session['username'])))


@app.route("/first_automation")
def first_automation():
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


@app.route('/success', methods=['GET', 'POST'])
def success():
    if 'username' in session:
        return render_template(
            'success.html',
            login="true",
            username=str(escape(session['username'])))


@app.route('/error', methods=['GET', 'POST'])
def error():
    if 'username' in session:
        return render_template('wizard.html', login="false")


@app.errorhandler(404)
def page_not_found(error):
    if 'username' in session:
        return render_template('wizard.html',
                               error="true",
                               username=str(escape(session['username']))), 404

    return load_home()


@app.route('/logout')
def logout():
    if session.get('username'):
        logger.info("Logging Out: " + str(escape(session['username'])))
        session.pop('username', None)
    return render_template('home.html')


if __name__ == '__main__':
    main()
