from bin import okta_verification
import flask
from flask import session, request, redirect, url_for, render_template
# from glob import escape
import json
import logging
import os
# import requests
import subprocess

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
# webhook_conf = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhook.conf'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

blueprint = flask.Blueprint('jawa_receiver', __name__, template_folder='templates')
logger = logging.getLogger('waitress')


def validate_webhook(webhook_data, webhook_name, webhook_user, webhook_pass):
    with open(jp_webhooks_file, "r") as fin:
        webhooks_json = json.load(fin)
    truth_test = False
    for each_webhook in webhooks_json:
        if each_webhook['name'] == webhook_name:
            truth_test = True
            if (
                    each_webhook['webhook_username'] != webhook_user or
                    each_webhook['webhook_password'] != webhook_pass):
                truth_test = False

    return truth_test


def run_script(webhook_data, webhook_name):
    with open(jp_webhooks_file, "r") as fin:
        webhooks_json = json.load(fin)
    for each_webhook in webhooks_json:
        if each_webhook['name'] == webhook_name:
            subprocess.Popen([each_webhook['script'], f"{webhook_data}"])


@blueprint.route('/hooks/<webhook_name>', methods=['POST', 'GET'])
def jamf_webhook_handler(webhook_name):
    print(webhook_name)
    webhook_data = request.get_json()
    if request.headers.get('x-okta-verification-challenge'):
        print("This is an Okta verification challenge...")
        return okta_verification.verify_new_webhook(request.headers.get('x-okta-verification-challenge'))

    auth = request.authorization
    webhook_user = "null"
    webhook_pass = "null"
    if auth:  # .get("username"):
        webhook_user = auth.get("username")
        webhook_pass = auth.get("password")

    # Debug
    # print(f"Webhook user: {webhook_user}\n"
    #       f"Webhook password: {webhook_pass}\n"
    #       f"Webhook name: {webhook_name}\n"
    #       f"Webhook data: {webhook_data}")

    if validate_webhook(webhook_data, webhook_name, webhook_user, webhook_pass):
        print(f"{webhook_name} validated!")
        run_script(webhook_data, webhook_name)
    else:
        print(f"{webhook_name} not validated!")

    return webhook_data
