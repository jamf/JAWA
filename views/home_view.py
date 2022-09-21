import base64
import json
import os
from collections import defaultdict

import requests
from flask import (Blueprint, escape, redirect, render_template,
                   request, session, url_for)

from bin import logger
from bin.tokens import get_token, invalidate_token

logthis = logger.setup_child_logger('jawa', __name__)

log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log'))
server_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
cron_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'cron.json'))
resources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources'))
files_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'files'))
img_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'img'))
verify_ssl = True  # Enables Jamf Pro SSL certificate verification

blueprint = Blueprint('home_view', __name__, template_folder='templates')


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if os.path.isfile(server_file):
            with open(server_file) as json_file:
                server_json = json.load(json_file)
            if request.form.get('active_url'):
                session['url'] = str(request.form.get('active_url'))
            elif server_json.get('jps_url', 0):
                if server_json['jps_url'] is not None and len(server_json['jps_url']) != 0:
                    session['url'] = str(server_json['jps_url'])
            elif request.form.get('url')[-1:] == "/":
                session['url'] = str(request.form.get('url')).rstrip(request.form.get('url')[-1])
            else:
                session['url'] = request.form['url']

        elif request.form.get('active_url')[-1:] == "/":
            session['url'] = str(request.form.get('url')).rstrip(request.form.get('url')[-1])
        else:
            session['url'] = request.form['url']
        session['username'] = request.form['username']
        session['password'] = request.form['password']
        session['b64_auth'] = base64.b64encode(str.encode(f"{session.get('username')}:{session.get('password')}"))
        get_token()
        logthis.info(f"[{session.get('url')}] Attempting login for: {session.get('username')}")

        if request.form['password'] == "":
            title = "Authentication error"
            msg = "Passwords can't be blank"
            return redirect(url_for('home_view.logout', error_title=title, error_message=msg))
        try:
            resp = requests.get(
                session['url'] + '/JSSResource/activationcode',
                headers={'Accept': 'application/json', "Authorization": f"Bearer {session['token']}",
                         'User-Agent': 'JAWA%20v3.0.3'},
                verify=verify_ssl)

            resp.raise_for_status()

        except requests.exceptions.HTTPError as err:
            logthis.info(f"Error occurred: {err}")
            return redirect(url_for('home_view.logout', error_title="Login error",
                                    error_message="check account credentials and privileges"))
        except requests.exceptions.ConnectTimeout as err:
            logthis.info(f"Error occurred: {err}")
            return redirect(url_for('home_view.logout', error_title="Connection Timeout", error_message=err))
        except requests.exceptions.ConnectionError as err:
            logthis.info(f"Error occurred: {err}")
            return redirect(url_for('home_view.logout', error_title="HTTP Error", error_message=err))

        logthis.info(
            f"[{session.get('url')}] Logging In: " + str(escape(session['username'])))

        return redirect(url_for('home_view.dashboard'))

    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))

    return redirect(url_for('home_view.dashboard'))


@blueprint.route('/logout')
def logout():
    error_title = request.args.get('error_title')
    error_message = request.args.get('error_message')
    if session.get('username'):
        invalidate_token()
        logthis.info("Logging Out: " + str(escape(session['username'])))
        session.pop('username', None)
    return load_home(error_title, error_message)


def load_home(error_title="", error_message=""):
    if 'username' in session:
        return redirect(url_for('home_view.dashboard'))
    if not os.path.isfile(server_file):
        with open(server_file, "w") as fout:
            json.dump({}, fout)

    with open(server_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    brand = server_json.get("brand")

    if (
            'jps_url' not in server_json
            or server_json['jps_url'] is None
            or len(server_json['jps_url']) == 0
    ):
        return render_template('home.html', app_name=brand)
    if 'alternate_jps' not in server_json:
        return render_template('home.html', app_name=brand, error_title=error_title, error_message=error_message)

    if server_json['alternate_jps'] != "":
        return render_template('home.html',
                               jps_url=server_json['jps_url'],
                               jps_url2=server_json['alternate_jps'],
                               welcome="true", jsslock="true", app_name=brand, error_title=error_title,
                               error_message=error_message)

    session['url'] = server_json['jps_url']
    return render_template('home.html',
                           jps_url=str(escape(session['url'])),
                           welcome="true", jsslock="true", app_name=brand, error_title=error_title,
                           error_message=error_message)


@blueprint.route("/dashboard")
def dashboard():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username')} rendering /dashboard.")
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

    with open(cron_file, "r") as cron_json:
        try:
            cron_list = json.load(cron_json)
        except json.decoder.JSONDecodeError as err:
            with open(cron_file, "w") as cron_json:
                cron_list = []
                json.dump(cron_list, cron_json, indent=4)

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
    logthis.info(f"Total webhooks managed by JAWA: {len(webhooks_installed)}")
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


@blueprint.route('/home.html')
def index():
    return load_home()
