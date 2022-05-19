from collections import defaultdict
from flask import (Blueprint, redirect, request, session, url_for)
import json
import os
import requests
import time

from bin import logger
from bin.view_modifiers import response

logthis = logger.setup_child_logger('jawa', __name__)

blueprint = Blueprint('webhooks', __name__, template_folder='templates')

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
okta_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'okta_json.json'))
okta_verification_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'okta_verification.py'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@blueprint.route('/webhooks/delete', methods=['GET', 'POST'])
@response(template_file='webhooks/delete.html')
def delete_webhook():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    target_webhook = request.args.get('target_webhook')
    if not target_webhook:
        return redirect(url_for('custom_webhook.custom_webhook'))
    with open(webhooks_file) as fin:
        webhook_json = json.load(fin)
    tag = [each_webhook['tag'] for each_webhook in webhook_json if each_webhook['name'] == target_webhook]

    if request.method == 'POST':
        logthis.info(f"Deleting {tag} webhook: {target_webhook}")
        for each_webhook in webhook_json:
            if each_webhook['name'] == target_webhook:
                script_file = each_webhook['script']
                if os.path.exists(script_file):
                    os.rename(script_file, f"{script_file}.old")
                if each_webhook['tag'] == 'jamfpro':
                    data = f"<webhook><name>{each_webhook['name']}.old.{time.time()}</name>" \
                           f"<enabled>false</enabled></webhook>"
                    full_url = f"{session['url']}/JSSResource/webhooks/name/{each_webhook['name']}"
                    webhook_response = requests.put(full_url,
                                                    auth=(session['username'], session['password']),
                                                    headers={'Content-Type': 'application/xml'},
                                                    data=data)
                elif each_webhook['tag'] == 'okta':
                    try:
                        response = requests.post(
                            f"{each_webhook.get('okta_url')}/api/v1/eventHooks/{each_webhook.get('okta_id')}/lifecycle/deactivate",
                            headers={"Authorization": "SSWS {}".format(each_webhook.get('okta_token'))})
                        response2 = requests.delete(
                            f"{each_webhook.get('okta_url')}/api/v1/eventHooks/{each_webhook.get('okta_id')}",
                            headers={"Authorization": "SSWS {}".format(each_webhook.get('okta_token'))})
                    except requests.exceptions.MissingSchema as err:
                        return redirect(url_for('error', error=err, username=session.get('username')))


                webhook_json.remove(each_webhook)
                with open(webhooks_file, 'w') as fout:
                    json.dump(webhook_json, fout, indent=4)
        return redirect(url_for('webhooks.webhooks'))
    return {'username': session.get('username'), 'target_webhook': target_webhook, 'tag': tag[0]}


@blueprint.route('/webhooks', methods=['GET', 'POST'])
@response(template_file='webhooks/home.html')
def webhooks():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    jamf_pro_webhooks_list = []
    okta_webhooks_list = []
    custom_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "custom":
            custom_webhooks_list.append(each_webhook)
        elif tag == 'jamfpro':
            jamf_pro_webhooks_list.append(each_webhook)
        elif tag == 'okta':
            okta_webhooks_list.append(each_webhook)
    return {'username': session.get('username'), 'custom_list': custom_webhooks_list,
            'jamf_list': jamf_pro_webhooks_list, 'okta_list': okta_webhooks_list, 'url': session.get('url')}
