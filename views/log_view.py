from datetime import datetime
import re
import subprocess
from time import sleep

from bin.load_home import load_home
from bin.view_modifiers import response
from main import jawa_logger

import flask
from flask import current_app, session, render_template, Blueprint, send_file
import os

log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log'))
server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))

blueprint = Blueprint('log_view', __name__, template_folder='templates')


@blueprint.route('/log/home.html', methods=['GET'])
def log_page():
    if not 'username' in session:
        return load_home()
    jawa_logger().info(f"/log/view accessed by {session.get('username') or 'nobody'}")
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
    return render_template('log/home.html', username=session.get('username'), log=lines)


@blueprint.route('/log/view', methods=['GET'])
def log_view():
    if not 'username' in session:
        return load_home()
    jawa_logger().info(f"/log/view accessed by {session.get('username') or 'nobody'}")
    with open(log_file, 'r') as fin:
        lines = [re.sub('\n', '', line) for line in fin.readlines()]
    return render_template('log/home.html', username=session.get('username'), log=lines)


@blueprint.route('/log/live.html', methods=['GET'])
@response(template_file="log/live.html")
def stream():
    if not 'username' in session:
        return render_template('home.html')
    current_user = session.get('username') or 'nobody'
    jawa_logger().info(f"/logview accessed by {session.get('username') or 'nobody'}")


    def generate():
        with open(log_file) as f:
            while True:
                yield f.read()

    return current_app.response_class(generate(), mimetype='text/plain')


@blueprint.route('/log/yield')
def yield_log():
    jawa_logger().info(f"/log/yield accessed by {session.get('username') or 'nobody'}")

    def inner():
        proc = subprocess.Popen(
            [f'tail -f {log_file}'],  # call something with a lot of output so we can see it
            shell=True,
            stdout=subprocess.PIPE
        )

        for line in iter(proc.stdout.readline, ''):
            sleep(.1)  # Don't need this just shows the text streaming
            yield line.rstrip().decode() + '<br/>\n'

    return flask.Response(inner(), mimetype='text/html')


@blueprint.route('/log/download')
def download_logs():
    timestamp = datetime.now()
    jawa_logger().info(f"Downloading log file...{timestamp}-jawa.log")
    return send_file(log_file, as_attachment=True, attachment_filename=f"{datetime.now()}-jawa.log")