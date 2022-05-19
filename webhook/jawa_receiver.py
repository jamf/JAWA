from flask import Blueprint, request
import json
import os
import subprocess

from bin import okta_verification
from bin import logger

logthis = logger.setup_child_logger('jawa', 'webhook_receiver')

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
jp_webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

blueprint = Blueprint('jawa_receiver', __name__, template_folder='templates')


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
            return script_results(webhook_data, each_webhook)


def script_results(webhook_data, each_webhook):
    webhook_data = json.dumps(webhook_data)
    proc = subprocess.Popen([each_webhook['script'], f"{webhook_data}"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output = proc.stdout.read()
    for each_line in output.decode().split('\n'):
        if each_line:
            logthis.info(f"{each_webhook.get('name')} - {each_line}")
    return output


@blueprint.route('/hooks/<webhook_name>', methods=['POST', 'GET'])
def webhook_handler(webhook_name):
    logthis.info(f"Incoming request at /hooks/{webhook_name} ...")
    webhook_data = request.get_json()
    if request.headers.get('x-okta-verification-challenge'):
        logthis.info("This is an Okta verification challenge...")
        return okta_verification.verify_new_webhook(request.headers.get('x-okta-verification-challenge'))
    if request.method != 'POST':
        logthis.info(f"Invalid request, {request.method} for /hooks/{webhook_name}.")
        return "405 - Method not allowed. These aren't the droids you're looking for. You can go about your business. " \
               "Move along.", 405
    webhook_user = "null"
    webhook_pass = "null"
    auth = request.authorization
    if auth:
        webhook_user = auth.get("username")
        webhook_pass = auth.get("password")

    if validate_webhook(webhook_data, webhook_name, webhook_user, webhook_pass):
        logthis.info(f"Validated authentication for /hooks/{webhook_name}, running script...")
        output = run_script(webhook_data, webhook_name)
        return {"webhook": f"{webhook_name}", "result": f"{output}"}, 202
    else:
        logthis.info(f"401 - Incorrect authentication provided for /hooks/{webhook_name}.")
        return f"Unauthorized - incorrect authentication provided for /hooks/{webhook_name}.", 401
