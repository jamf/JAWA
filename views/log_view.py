from datetime import datetime
import flask
from flask import (Blueprint, current_app, escape, redirect, render_template, Response,
                   request, send_file, session, url_for)
import os
import re
import subprocess
from time import sleep

from bin.view_modifiers import response
from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)

log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log'))
server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))

blueprint = Blueprint('log_view', __name__, template_folder='templates')


@blueprint.route('/log/home.html', methods=['GET'])
def log_home():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.debug(f"[{session.get('url')}] {session.get('username').title()} viewed {request.path}")
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
        lines.reverse()
        view_lines = lines[:500]
    return render_template('log/home.html', username=session.get('username'), log=view_lines)


@blueprint.route('/log/view', methods=['GET'])
def log_view():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.debug(f"[{session.get('url')}] {session.get('username').title()} viewed {request.path}")
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
        lines.reverse()
        view_lines = lines[:500]
    return render_template('log/home.html', username=session.get('username'), log=view_lines)


@blueprint.route('/log/live.html', methods=['GET'])
@response(template_file="log/live.html")
def stream():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.debug(f"[{session.get('url')}] {session.get('username').title()} viewed {request.path}")

    def generate():
        with open(log_file) as f:
            while True:
                yield f.read()

    return current_app.response_class(generate(), mimetype='text/plain')


@blueprint.route('/log/yield')
def yield_log():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"/log/yield accessed by {session.get('username') or 'nobody'}")

    def inner():
        proc = subprocess.Popen(
            [f'tail -f {log_file}'],  # call something with a lot of output so we can see it
            shell=True,
            stdout=subprocess.PIPE
        )

        for line in iter(proc.stdout.readline, ''):
            sleep(.1)  # Don't need this just shows the text streaming
            yield line.rstrip().decode() + '<br/>\n'

    return Response(inner(), mimetype='text/html')


@blueprint.route('/log/download')
def download_logs():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username')} used {request.path} to download the log.")
    timestamp = datetime.now()
    logthis.info(f"Downloading log file...{timestamp}-jawa.log")
    return send_file(log_file, as_attachment=True, attachment_filename=f"{datetime.now()}-jawa.log")
