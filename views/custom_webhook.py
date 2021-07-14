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

blueprint = Blueprint('custom_webhook', __name__, template_folder='templates')

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
okta_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'okta_json.json'))
okta_verification_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'okta_verification.py'))
webhooks_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@blueprint.route('/webhooks/custom', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/home.html')
def custom_webhook():
    if not 'username' in session:
        return redirect(url_for('logout'))
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    custom_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data['tag']
        if tag == "custom":
            custom_webhooks_list.append(each_webhook)
    print(custom_webhooks_list)

    return {'username': session.get('username'),
            'custom_list': custom_webhooks_list}


@blueprint.route('/webhooks/custom/edit', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/edit.html')
def edit_webhook():
    if 'username' not in session:
        return redirect(url_for('logout'))
    name = request.args.get('name')
    print(name)
    with open(webhooks_file) as fin:
        webhooks_json = json.load(fin)
    check_for_name = [True for each_webhook in webhooks_json if each_webhook['name'] == name]
    print(check_for_name)
    if not check_for_name:
        jawa_logger().info("name not in json")
        return redirect(url_for('custom_webhook.custom_webhook'))
    if request.method == 'POST':
        # print(name)
        button_choice = request.form.get('button_choice')
        if button_choice == 'Delete':
            return redirect(url_for('webhooks.delete_webhook', target_webhook=name))

        check_for_name = [True for each_webhook in webhooks_json if each_webhook['name'] == name]
        print(check_for_name)
        if not check_for_name:
            print("name not in json")
        for each_webhook in webhooks_json:
            if each_webhook['name'] == name:
                new_custom_name = request.form.get('custom_name')
                if not new_custom_name:
                    new_custom_name = name
                description = request.form.get('description')
                if request.files.get('new_file'):
                    new_script = request.files.get('new_file')
                    owd = os.getcwd()
                    os.chdir(scripts_dir)

                    if ' ' in new_script.filename:
                        new_script.filename = new_script.filename.replace(" ", "-")

                    new_filename = f"{new_custom_name}-{new_script.filename}"
                    new_script.save(secure_filename(new_filename))
                    new_filename = os.path.join(scripts_dir, f"{new_custom_name}-{new_script.filename}")
                    os.chmod(new_filename, mode=0o0755)
                    os.chdir(owd)
                    each_webhook['script'] = new_filename
                if new_custom_name:
                    each_webhook['name'] = new_custom_name
                if description:
                    each_webhook['description'] = description

                with open(webhooks_file, 'w') as fout:
                    json.dump(webhooks_json, fout, indent=4)
                return redirect(url_for('custom_webhook.custom_webhook'))

    return {'username': session.get('username'), 'webhook_name': name}


@blueprint.route('/webhooks/custom/new', methods=['GET', 'POST'])
@response(template_file='webhooks/custom/new.html')
def new_webhook():
    if not 'username' in session:
        return redirect(url_for('logout'))
    if request.method == 'POST':
        new_custom_name = request.form.get('custom_name')
        description = request.form.get('description')
        if request.form.get('custom_name') != '':
            check = 0
            print(request.form.get('custom_name'))

            with open(webhooks_file, 'r') as json_file:
                webhooks_json = json.load(json_file)
            if webhooks_json:
                for each_webhook in webhooks_json:

                    if each_webhook.get('name') == new_custom_name:
                        check = 1
            owd = os.getcwd()
            os.chdir(scripts_dir)
            target_file = request.files.get('new_file')

            if ' ' in target_file.filename:
                target_file.filename = target_file.filename.replace(" ", "-")

            new_filename = f"{new_custom_name}-{target_file.filename}"
            target_file.save(secure_filename(new_filename))
            new_filename = os.path.join(scripts_dir, f"{new_custom_name}-{target_file.filename}")
            os.chmod(new_filename, mode=0o0755)
            os.chdir(owd)
            if check != 0:
                error_message = "Name already exists!"
                print(error_message)
                return {"error": error_message, "username": session.get('username'), 'name': new_custom_name,
                        'description': description}

            webhooks_json.append({"url": str(session['url']),
                                  "jawa_admin": str(session['username']),
                                  "name": new_custom_name,
                                  "webhook_username": request.form.get('username', 'null'),
                                  "webhook_password": request.form.get('password', 'null'),
                                  # "event": request.form.get('event'),
                                  "script": new_filename,
                                  "description": description,
                                  "tag": "custom"})

            with open(webhooks_file, 'w') as outfile:
                json.dump(webhooks_json, outfile, indent=4)

            return redirect(url_for('custom_webhook.custom_webhook'))
    return {'username': session.get('username')}
