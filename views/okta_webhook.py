# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2023 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

from collections import defaultdict
import json
from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape
import os
from typing import Any, Dict, Union

import requests
from werkzeug.utils import secure_filename

from bin.view_modifiers import response
from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)

blueprint = Blueprint('okta_webhook', __name__)

server_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json')
)
okta_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'okta_json.json')
)
okta_verification_file = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), '..', 'bin', 'okta_verification.py'
    )
)
webhooks_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'webhooks.json')
)
scripts_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'scripts')
)


@blueprint.route('/webhooks/okta', methods=['GET', 'POST'])
@response(template_file='webhooks/okta/home.html')
def okta_webhook() -> Union[Response, Dict[str, Any]]:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    with open(webhooks_file, 'r') as fin:
        webhooks_json = json.load(fin)
    okta_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: 'MISSING', each_webhook)
        tag = data['tag']
        if tag == 'okta':
            okta_webhooks_list.append(each_webhook)
    return {
        'key': 'Have a good weekend my dude.',
        'username': session.get('username'),
        'okta_list': okta_webhooks_list,
    }


@blueprint.route('/webhooks/okta/new', methods=['GET', 'POST'])
def okta_new() -> Union[Response, str]:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    os.chmod(okta_verification_file, mode=0o0755)
    if not os.path.isfile(webhooks_file):
        data = []
        with open(webhooks_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)
    with open(server_json_file) as json_file:
        data = json.load(json_file)
        server_address = data.get('jawa_address')
        if not server_address:
            return redirect(url_for('setup'))
    if request.method != 'POST':
        return render_template(
            'webhooks/okta/new.html',
            setup='setup',
            username=str(escape(session['username'])),
        )
    if ' ' in request.form.get('webhookname'):
        error_message = 'Single-string name only.'
        return render_template(
            'error.html',
            error_message=error_message,
            error='error',
            username=str(escape(session['username'])),
        )
    if not os.path.isdir(scripts_dir):
        os.mkdir(scripts_dir)

    okta_server = request.form.get('okta_server')
    okta_token = request.form.get('token')
    okta_name = request.form.get('webhookname')
    okta_event = request.form.get('event')
    description = request.form.get('description')
    webhook_server_url = server_address + '/hooks/' + okta_name
    logthis.info(webhook_server_url)
    owd = os.getcwd()
    os.chdir(scripts_dir)

    f = request.files['script']
    if ' ' in f.filename:
        f.filename = f.filename.replace(' ', '-')

    f.save(secure_filename(f.filename))

    old_script_file = os.path.join(scripts_dir, f.filename)
    data = json.load(open(webhooks_file))
    script_file = os.path.join(scripts_dir, okta_name + '_' + f.filename)
    os.rename(old_script_file, script_file)
    new_file = script_file
    okta_info = json.load(open(webhooks_file))
    os.chdir(owd)
    for i in data:
        if str(i['name']) == okta_name:
            error_message = 'Name already exists!'
            logthis.info('okta webhook erorr')
            return render_template(
                'error.html',
                error_message=error_message,
                error='error',
                username=str(escape(session['username'])),
            )

    os.chmod(os.path.join(scripts_dir, new_file), mode=0o0755)

    data = {
        'name': okta_name,
        'events': {'type': 'EVENT_TYPE', 'items': [okta_event]},
        'channel': {
            'type': 'HTTP',
            'version': '1.0.0',
            'config': {
                'uri': webhook_server_url,
                'headers': [
                    {'key': 'X-Other-Header', 'value': 'some-other-value'}
                ],
                'authScheme': {
                    'type': 'HEADER',
                    'key': 'Authorization',
                    'value': '${api_key}',
                },
            },
        },
    }

    data = json.dumps(data, indent=4)

    # Makes hook in Okta, gets id
    resp = requests.post(
        f'{okta_server}/api/v1/eventHooks',
        headers={
            'Accept': 'application/json',
            'Authorization': f'SSWS {okta_token}',
            'Content-Type': 'application/json',
        },
        data=data,
    )
    response_json = resp.json()
    okta_id = response_json.get('id')

    okta_info.append(
        {
            'name': okta_name,
            'okta_id': okta_id,
            'okta_event': okta_event,
            'okta_url': okta_server,
            'okta_token': okta_token,
            'script': script_file,
            'description': description,
            'webhook_username': 'null',
            'webhook_password': 'null',
            'tag': 'okta',
        }
    )
    if okta_id:
        with open(webhooks_file, 'w') as outfile:
            json.dump(okta_info, outfile, indent=4)

    # Verify/activate
    resp = requests.post(
        f'{okta_server}/api/v1/eventHooks/{okta_id}/lifecycle/verify',
        headers={'Authorization': f'SSWS {okta_token}'},
    )
    verification = resp.json()
    if 'errorCode' in verification:
        error_message = (
            'Okta was unable to verify the webhook.  Check network settings.'
        )
        return render_template(
            'error.html',
            error_message=error_message,
            error='Event Verification Error',
            username=str(escape(session['username'])),
        )

    return render_template(
        'success.html',
        username=session.get('username'),
        login='true',
        success_msg='Okta Webhook Created.',
    )
