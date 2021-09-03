#!/usr/bin/python3
# encoding: utf-8
from collections import defaultdict
from datetime import timedelta

from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape)
import glob
import json
import logging
from logging import handlers
import os
import requests
from waitress import serve

from bin.view_modifiers import response


def jawa_logger():
    global logger
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'jawa.log'))
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('jawa')
    logger.setLevel(logging.INFO)
    handler = handlers.RotatingFileHandler(log_file, maxBytes=(1048576 * 100), backupCount=10)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    return logger


# Flask logging
jawa_logger()
error_message = ""
verify_ssl = True  # Enables Jamf Pro SSL certificate verification

# Initiate Flask
app = Flask(__name__)


# Session heartbeat
@app.before_request
def func():
    session.modified = True


def main():
    base_dir = os.path.dirname(__file__)
    jawa_logger().info(f"JAWA initializing...\n Sandcrawler home:  {base_dir}")
    environment_setup(base_dir)
    register_blueprints()
    app.secret_key = "untini"
    app.permanent_session_lifetime = timedelta(minutes=10)
    serve(app, url_scheme='https', host='0.0.0.0', port=8000)


def environment_setup(project_dir):
    global webhooks_file, cron_file, server_json_file, scripts_directory
    webhooks_file = os.path.abspath(os.path.join(project_dir, 'data', 'webhooks.json'))
    cron_file = os.path.abspath(os.path.join(project_dir, 'data', 'cron.json'))
    server_json_file = os.path.abspath(os.path.join(project_dir, 'data', 'server.json'))
    scripts_directory = os.path.abspath(os.path.join(project_dir, 'scripts'))
    jawa_logger().info(f"Detecting JAWA environment:\n"
                       f"Webhooks configuration file: {webhooks_file}\n"
                       f"Cron configuration file: {cron_file}\n"
                       f"Server configuration file: {server_json_file}\n"
                       f"Scripts directory: {scripts_directory}")


def register_blueprints():
    # JAWA Receiver
    from webhook import jawa_receiver
    app.register_blueprint(jawa_receiver.blueprint)
    # Jamf Pro Webhooks view
    from views import jamf_webhook
    app.register_blueprint(jamf_webhook.blueprint)
    # Okta Webhooks view
    from views.okta_webhook import blueprint
    app.register_blueprint(blueprint)
    # Create a new Cron Job
    from views.cron_views import blueprint
    app.register_blueprint(blueprint)
    # Log view
    from views import log_view
    app.register_blueprint(log_view.blueprint)
    # Resources (aka files) view
    from views import resource_view
    app.register_blueprint(resource_view.blueprint)
    # Custom Webhooks view
    from views import custom_webhook
    app.register_blueprint(custom_webhook.blueprint)
    # Webhooks Base view
    from views import webhook_view
    app.register_blueprint(webhook_view.blueprint)


# Server setup including making .json file necessary for webhooks


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if 'username' in session:
        if request.method == 'POST':
            jawa_logger().debug(f"[{session.get('url')}] {session.get('username')} /setup - POST")
            server_url = request.form.get('address')
            jps_url = request.form.get('jss-lock')
            jps2_check = request.form.get('alternate-jamf')
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
            jawa_logger().debug(f"[{session.get('url')}] {session.get('username')} - /setup - GET")
            if not os.path.isfile(server_json_file):
                with open(server_json_file, "w") as outfile:
                    server_json = {'jawa_address': '', 'jps_url': '', 'alternate_jps': ''}
                    json.dump(server_json, outfile)
            with open(server_json_file, "r") as fin:
                server_json = json.load(fin)
            jps_url2 = server_json.get('alternate_jps')
            if jps_url2 == str(escape(session['url'])):
                primary_jps = server_json['jps_url']
            else:
                primary_jps = str(escape(session['url']))
            jawa_url = server_json.get('jawa_address')
            return render_template('setup/setup.html',
                                   login="false", jps_url=primary_jps, jps_url2=jps_url2,
                                   jawa_url=jawa_url, username=session.get('username'))
    else:
        return redirect(url_for('logout'))


@app.route("/cleanup", methods=['GET', 'POST'])
@response(template_file="setup/cleanup.html")
def cleanup():
    if 'username' not in session:
        return redirect(url_for('logout'))
    if request.method == 'POST':
        logger.info(f"[{session.get('url')}] {session.get('username')} is cleaning up scripts...")
        owd = os.getcwd()
        if not os.path.isdir(scripts_directory):
            os.mkdir(scripts_directory)
        os.chdir(scripts_directory)
        for file in glob.glob("*.old"):
            logger.info(f"[{session.get('url')}] {session.get('username')} removed the script {file}...")
            os.remove(file)
        os.chdir(owd)
        return redirect(url_for('success'))

    else:
        return {"username": session.get('username'), "scripts_dir": scripts_directory}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if os.path.isfile(server_json_file):
            with open(server_json_file) as json_file:
                server_json = json.load(json_file)
            if request.form.get('active_url'):
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

        jawa_logger().info(f"[{session.get('url')}] Attempting login for: {session.get('username')}")

        if request.form['password'] != "":
            try:
                resp = requests.get(
                    session['url'] + '/JSSResource/activationcode',
                    auth=(session['username'], session['password']),
                    headers={'Accept': 'application/json'},
                    verify=verify_ssl)

                resp.raise_for_status()

            except requests.exceptions.HTTPError as err:
                return redirect(url_for('logout'))

            response_json = resp.json()

            jawa_logger().info(
                f"[{session.get('url')}] Logging In: " + str(escape(session['username'])))

            return redirect(url_for('dashboard'))

        else:
            return redirect(url_for('logout'))
    if 'username' not in session:
        return redirect(url_for('logout'))

    return redirect(url_for('dashboard'))


@app.route('/')
@app.route('/home.html')
def index():
    return load_home()


def load_home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    if not os.path.isfile(server_json_file):
        with open(server_json_file, "w") as fout:
            json.dump({}, fout)

    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    else:
        brand = server_json.get("brand")

        if not 'jps_url' in server_json:
            return render_template('home.html', app_name=brand)
        elif server_json['jps_url'] is None:
            return render_template('home.html', app_name=brand)
        elif len(server_json['jps_url']) == 0:
            return render_template('home.html', app_name=brand)
        else:
            if 'alternate_jps' not in server_json:
                return render_template('home.html', app_name=brand)

            if server_json['alternate_jps'] != "":
                return render_template('home.html',
                                       jps_url=server_json['jps_url'],
                                       jps_url2=server_json['alternate_jps'],
                                       welcome="true", jsslock="true", app_name=brand)

            session['url'] = server_json['jps_url']
            return render_template('home.html',
                                   jps_url=str(escape(session['url'])),
                                   welcome="true", jsslock="true", app_name=brand)


@app.route("/")
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    else:
        with open(server_json_file) as json_file:
            server_json = json.load(json_file)
        # print(server_json)
        if 'jps_url' not in server_json:
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


@app.route("/dashboard")
def dashboard():
    if 'username' not in session:
        return redirect(url_for('logout'))
    jawa_logger().info(f"[{session.get('url')}] {session.get('username')} rendering /dashboard.")
    with open(webhooks_file) as webhook_json:
        webhooks_installed = json.load(webhook_json)
    jamf_pro_webhooks = []
    okta_webhooks = []
    custom_webhooks = []
    for each_webhook in webhooks_installed:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "jamfpro":
            jamf_pro_webhooks.append(each_webhook)
        elif tag == "okta":
            okta_webhooks.append(each_webhook)
        elif tag == "custom":
            custom_webhooks.append(each_webhook)

    data = []

    if not os.path.isfile(cron_file):
        with open(cron_file, "w") as outfile:
            json.dump(data, outfile)

    with open(cron_file) as cron_json:
        cron_list = json.load(cron_json)
        cron_json = []
        for cron in cron_list:
            script = cron['script'].rsplit('/', 1)
            cron_json.append({"name": cron['name'],
                              "frequency": cron['frequency'],
                              "script": script[1],
                              "description": cron['description']})

    webhook_url = session['url']

    if not cron_json:
        cron_json = ''
    jawa_logger().info(f"Total webhooks managed by JAWA: {len(webhooks_installed)}")
    if webhook_json == cron_json:
        return redirect(url_for('first_automation'))
    return render_template(
        'dashboard.html',
        webhook_url=webhook_url,
        jamfpro_list=jamf_pro_webhooks,
        url=session.get('url'),
        cron_list=cron_json,
        okta_list=okta_webhooks,
        custom_list=custom_webhooks,
        total_webhooks=len(webhooks_installed),
        total_cron=len(cron_json),
        login="true",
        username=str(escape(session['username'])))


@app.route('/success', methods=['GET', 'POST'])
def success():
    if 'username' not in session:
        jawa_logger().info(f"No user logged in - returning to login page.")
        return redirect(url_for('logout'))
    return render_template(
        'success.html',
        login="true",
        username=str(escape(session['username'])))


@app.route('/error', methods=['GET', 'POST'])
def error():
    if 'username' not in session:
        return redirect(url_for('logout'))
    jawa_logger().info(
        f"[{session.get('url')}] {session.get('username').title()} was a victim of a series of accidents, as are we all. (/error)")
    return render_template('error.html', username=session.get('username'))


@app.errorhandler(404)
def page_not_found(error):
    if 'username' in session:
        jawa_logger().info(
            f"[{session.get('url')}] {session.get('username')} wandered off course  ({request.path}) - redirecting to /dashboard.")
        return redirect(url_for('dashboard'))
    jawa_logger().info(
        f"An invalid path ({request.path}) was provided and no user is logged in.  Returning login page.")
    return load_home()


@app.route('/logout')
def logout():
    if session.get('username'):
        logger.info("Logging Out: " + str(escape(session['username'])))
        session.pop('username', None)
    return load_home()


if __name__ == '__main__':
    main()
