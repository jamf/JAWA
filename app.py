# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2024 Jamf.  All rights reserved.
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

import glob
import json
import os
import uuid

from datetime import timedelta
from flask import (
    Flask,
    request,
    render_template,
    session,
    redirect,
    url_for,
    Response,
)
from markupsafe import escape
from waitress import serve
from typing import Any, Dict, Union

from bin import logger
from bin.view_modifiers import response
from views.home_view import load_home

# Flask logging
logthis = logger.setup_child_logger("jawa", "app")
error_message = ""

# Initiate Flask
app = Flask(__name__)


# Session heartbeat
@app.before_request
def func() -> None:
    session.modified = True


def main() -> None:
    base_dir = os.path.dirname(__file__)
    logthis.info(f"JAWA initializing...\n Sandcrawler home:  {base_dir}")
    environment_setup(base_dir)
    register_blueprints()
    app.secret_key = str(uuid.uuid4())
    app.permanent_session_lifetime = timedelta(minutes=10)
    serve(
        app, url_scheme="https", host="0.0.0.0", port=8000, threads=15
    )  # Serve me the sky with a big slice of lemon


def environment_setup(project_dir: str) -> None:
    global webhooks_file, cron_file, server_json_file, scripts_directory
    webhooks_file = os.path.abspath(
        os.path.join(project_dir, "data", "webhooks.json")
    )
    cron_file = os.path.abspath(os.path.join(project_dir, "data", "cron.json"))
    server_json_file = os.path.abspath(
        os.path.join(project_dir, "data", "server.json")
    )
    scripts_directory = os.path.abspath(os.path.join(project_dir, "scripts"))
    logthis.info(
        f"Detecting JAWA environment:\n"
        f"Webhooks configuration file: {webhooks_file}\n"
        f"Cron configuration file: {cron_file}\n"
        f"Server configuration file: {server_json_file}\n"
        f"Scripts directory: {scripts_directory}"
    )


def register_blueprints() -> None:
    # JAWA Receiver
    from webhook import jawa_receiver

    app.register_blueprint(jawa_receiver.blueprint)
    # Jamf Pro Webhooks view
    from views import jamf_webhook

    app.register_blueprint(jamf_webhook.blueprint)
    # Okta Webhooks view
    from views.okta_webhook import blueprint

    app.register_blueprint(blueprint)
    # Create a new Cron Job
    from views.cron_view import blueprint

    app.register_blueprint(blueprint)
    # Log view
    from views import log_view

    app.register_blueprint(log_view.blueprint)
    # Resources (aka files) view
    from views import resource_view

    app.register_blueprint(resource_view.blueprint)
    # Custom Webhooks view
    from views import custom_webhook

    app.register_blueprint(custom_webhook.blueprint)
    # Webhooks Base view
    from views import webhook_view

    app.register_blueprint(webhook_view.blueprint)
    # Home, Dashboard and Login view
    from views import home_view

    app.register_blueprint(home_view.blueprint)


# Server setup including making .json file necessary for webhooks
@app.route("/setup", methods=["GET", "POST"])
def setup() -> Union[Response, str]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    if request.method == "POST":
        logthis.debug(
            f"[{session.get('url')}] {session.get('username')} /setup - POST"
        )
        server_url = request.form.get("address")
        if not server_url:
            return redirect(url_for("setup"))
        jps_url = request.form.get("jss-lock")
        jps2_check = request.form.get("alternate-jamf")
        jps_url2 = request.form.get("alternate")
        logthis.info(
            f"{session.get('username')} made JAWA Setup Changes\n"
            f"JAWA URL: {server_url}\n"
            f"Primary JPS: {jps_url}\n"
            f"Alternate JPS: {jps_url2}\n"
            f"Alternate enabled?: {jps2_check}"
        )
        new_json = {}
        if server_url != "":
            new_json["jawa_address"] = server_url
        if jps_url != "":
            new_json["jps_url"] = jps_url
        if not os.path.isfile(server_json_file):
            with open(server_json_file, "w") as outfile:
                server_json = {
                    "jawa_address": server_url,
                    "jps_url": jps_url,
                    "alternate_jps": jps_url2,
                }
                json.dump(server_json, outfile)
        elif os.path.isfile(server_json_file):
            with open(server_json_file, "w") as outfile:
                server_json = {
                    "jawa_address": server_url,
                    "jps_url": jps_url,
                    "alternate_jps": jps_url2,
                }
                json.dump(server_json, outfile)
            with open(server_json_file, "r") as fin:
                data = json.load(fin)
            data.update(new_json)
            with open(server_json_file, "w+") as outfile:
                json.dump(data, outfile)

        return render_template(
            "success.html",
            webhooks="success",
            success_msg="JAWA Setup Complete!",
            username=str(escape(session["username"])),
        )
    else:
        logthis.debug(
            f"[{session.get('url')}] {session.get('username')} - /setup - GET"
        )
        if not os.path.isfile(server_json_file):
            with open(server_json_file, "w") as outfile:
                server_json = {
                    "jawa_address": "",
                    "jps_url": "",
                    "alternate_jps": "",
                }
                json.dump(server_json, outfile)
        with open(server_json_file, "r") as fin:
            server_json = json.load(fin)
        jps_url2 = server_json.get("alternate_jps")
        if jps_url2 == str(escape(session["url"])):
            primary_jps = server_json["jps_url"]
        else:
            primary_jps = str(escape(session["url"]))
        jawa_url = server_json.get("jawa_address")
        return render_template(
            "setup/setup.html",
            login="false",
            jps_url=primary_jps,
            jps_url2=jps_url2,
            jawa_url=jawa_url,
            username=session.get("username"),
        )


@app.route("/cleanup", methods=["GET", "POST"])
@response(template_file="setup/cleanup.html")
def cleanup() -> Union[Response, Dict[str, Any]]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    if request.method != "POST":
        owd = os.getcwd()
        if not os.path.isdir(scripts_directory):
            os.mkdir(scripts_directory)
        os.chdir(scripts_directory)
        old_scripts = glob.glob("*.old")
        os.chdir(owd)
        return {
            "username": session.get("username"),
            "scripts_dir": scripts_directory,
            "scripts": old_scripts,
        }
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} is cleaning up scripts..."
    )
    owd = os.getcwd()
    if not os.path.isdir(scripts_directory):
        os.mkdir(scripts_directory)
    os.chdir(scripts_directory)
    del_list = []
    for file in glob.glob("*.old"):
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} removed the script {file}..."
        )
        del_list.append(f"{file}")
        os.remove(file)
    os.chdir(owd)
    if not del_list:
        success_msg = "No Script files found to clean up."
    else:
        txt_list = "Deleted: \n"
        for file in del_list:
            txt_list += f"{file}\n"
        success_msg = txt_list or "No script files found to clean up."
    return redirect(url_for("success", success_msg=success_msg))


@app.route("/")
def home() -> Union[Response, str]:
    return load_home()


@app.route("/success", methods=["GET", "POST"])
def success(success_msg="") -> Union[Response, str]:
    if "username" not in session:
        logthis.info("No user logged in - returning to login page.")
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    success_msg = request.args.get("success_msg")
    if success_msg:
        success_msg = escape(success_msg)
    return render_template(
        "success.html",
        success_msg=success_msg,
        login="true",
        username=str(escape(session["username"])),
    )


@app.route("/error", methods=["GET", "POST"])
def error() -> Union[Response, str]:
    error_title = request.args.get("error")
    error_message = request.args.get("error_message")
    if error_title:
        error_title = escape(error_title)
    if error_message:
        error_message = escape(error_message)
    if "username" not in session:
        return redirect(url_for("home_view.logout"))
    logthis.info(
        f"[{session.get('url')}] {session.get('username').title()} was a victim of a series of accidents, as are we all. (/error)"
    )
    return render_template(
        "error.html",
        username=session.get("username"),
        error_message=error_title,
        error=error_message,
    )


@app.errorhandler(404)
def page_not_found() -> Union[Response, str]:
    if "username" in session:
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} wandered off course  ({request.path}) - redirecting to /dashboard."
        )
        return redirect(url_for("home_view.dashboard"))
    logthis.info(
        f"An invalid path ({request.path}) was provided and no user is logged in.  Returning login page."
    )
    return load_home()


if __name__ == "__main__":
    main()
