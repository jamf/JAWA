import os
import json
import glob
import time
from collections import defaultdict
from time import sleep
import requests
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

from bin.load_home import load_home
from bin.view_modifiers import response
from app import jawa_logger


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
        return redirect(url_for('logout'))
    target_webhook = request.args.get('target_webhook')
    if not target_webhook:
        return redirect(url_for('custom_webhook.custom_webhook'))
    with open(webhooks_file) as fin:
        webhook_json = json.load(fin)
    tag = [each_webhook['tag'] for each_webhook in webhook_json if each_webhook['name'] == target_webhook]

    if request.method == 'POST':
        jawa_logger().info(f"Deleting {tag} webhook: {target_webhook}")
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
                    response = requests.post(
                        f"{each_webhook.get('okta_url')}/api/v1/eventHooks/{each_webhook.get('okta_id')}/lifecycle/deactivate",
                        headers={"Authorization": "SSWS {}".format(each_webhook['okta_token'])})
                    response2 = requests.delete(
                        f"{each_webhook.get('okta_url')}/api/v1/eventHooks/{each_webhook.get('okta_id')}",
                        headers={"Authorization": "SSWS {}".format(each_webhook['okta_token'])})

                webhook_json.remove(each_webhook)
                with open(webhooks_file, 'w') as fout:
                    json.dump(webhook_json, fout, indent=4)
        return redirect(url_for('webhooks.webhooks'))

    print(target_webhook, tag[0])
    return {'username': session.get('username'), 'target_webhook': target_webhook, 'tag': tag[0]}


@blueprint.route('/webhooks', methods=['GET', 'POST'])
@response(template_file='webhooks/home.html')
def webhooks():
    if 'username' not in session:
        return redirect(url_for('logout'))
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
    print(okta_webhooks_list)
    return {'username': session.get('username'), 'custom_list': custom_webhooks_list,
            'jamf_list': jamf_pro_webhooks_list, 'okta_list': okta_webhooks_list, 'url': session.get('url')}
