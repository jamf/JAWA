# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2022 Jamf.  All rights reserved.
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

import os
import re
import subprocess
from datetime import datetime
from time import sleep
from typing import Union

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    Response,
    request,
    send_file,
    session,
    url_for,
)

from bin import logger
from bin.view_modifiers import response

logthis = logger.setup_child_logger('jawa', __name__)

log_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log')
)
server_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json')
)

blueprint = Blueprint('log_view', __name__, template_folder='templates')


@blueprint.route('/log/home.html', methods=['GET'])
def log_home() -> Union[Response, str]:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    logthis.debug(
        f'[{session.get("url")}] {session.get("username").title()} viewed {request.path}'
    )
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
        lines.reverse()
        view_lines = lines[:500]
    return render_template(
        'log/home.html', username=session.get('username'), log=view_lines
    )


@blueprint.route('/log/view', methods=['GET'])
def log_view() -> Union[Response, str]:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    logthis.debug(
        f'[{session.get("url")}] {session.get("username").title()} viewed {request.path}'
    )
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
        lines.reverse()
        view_lines = lines[:500]
    return render_template(
        'log/home.html', username=session.get('username'), log=view_lines
    )


@blueprint.route('/log/live.html', methods=['GET'])
@response(template_file='log/live.html')
def stream() -> Response:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    logthis.debug(
        f'[{session.get("url")}] {session.get("username").title()} viewed {request.path}'
    )

    def generate():
        with open(log_file) as f:
            while True:
                yield f.read()

    return current_app.response_class(generate(), mimetype='text/plain')


@blueprint.route('/log/yield')
def yield_log() -> Response:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    logthis.info(
        f'/log/yield accessed by {session.get("username") or "nobody"}'
    )

    def inner():
        proc = subprocess.Popen(
            [
                f'tail -f {log_file}'
            ],  # call something with a lot of output so we can see it
            shell=True,
            stdout=subprocess.PIPE,
        )

        for line in iter(proc.stdout.readline, ''):
            sleep(0.1)  # Don't need this just shows the text streaming
            yield line.rstrip().decode() + '<br/>\n'

    return Response(inner(), mimetype='text/html')


@blueprint.route('/log/download')
def download_logs() -> Response:
    if 'username' not in session:
        return redirect(
            url_for(
                'home_view.logout',
                error_title='Session Timed Out',
                error_message='Please sign in again',
            )
        )
    logthis.info(
        f'[{session.get("url")}] {session.get("username")} used {request.path} to download the log.'
    )
    timestamp = datetime.now()
    logthis.info(f'Downloading log file...{timestamp}-jawa.log')
    return send_file(
        log_file,
        as_attachment=True,
        download_name=f'{datetime.now()}-jawa.log',
    )
