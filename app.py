# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2026 Jamf.  All rights reserved.
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
from typing import Any, Dict, Tuple, Union

from bin import logger
from bin.context_processors import inject_common_vars, register_static_cache_bust
from bin.view_modifiers import response
from views.home_view import _strip_trailing_slash, load_home

# Flask logging
logthis = logger.setup_child_logger("jawa", "app")
error_message = ""

SESSION_TIMEOUT_CHOICES = (15, 60, 240, 480)
DEFAULT_SESSION_TIMEOUT = 15


def _resolve_session_timeout(config: dict) -> int:
    """Resolve the configured session timeout (minutes) against the
    allowed ladder. Any missing / malformed / off-ladder value fails
    safe to the 15-minute default (never longer)."""
    value = config.get("session_timeout_minutes")
    if type(value) is int and value in SESSION_TIMEOUT_CHOICES:
        return value
    return DEFAULT_SESSION_TIMEOUT

# Initiate Flask
app = Flask(__name__)
# Secure cookies require HTTPS. JAWA runs HTTPS behind nginx in
# production, so Secure defaults on. A Secure cookie is dropped by the
# browser over plain http, which breaks local `python3 app.py` runs
# (login succeeds but the session cookie never returns -> login loop).
# Set JAWA_INSECURE_COOKIES=1 for local http development only.
_secure_cookies = os.environ.get("JAWA_INSECURE_COOKIES") != "1"
app.config.update(
    SESSION_COOKIE_SECURE=_secure_cookies,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)


# Session heartbeat: slide the window and apply the admin-configured
# timeout (fail-safe to 15 min) on every request, so a /setup change
# takes effect immediately with no restart.
@app.before_request
def _session_heartbeat() -> None:
    from bin import data_store

    minutes = _resolve_session_timeout(data_store.get_server_config())
    app.permanent_session_lifetime = timedelta(minutes=minutes)
    session.modified = True


app.context_processor(inject_common_vars)
register_static_cache_bust(app)


def main() -> None:
    base_dir = os.path.dirname(__file__)
    logthis.info(f"JAWA initializing...\n Sandcrawler home:  {base_dir}")
    try:
        environment_setup(base_dir)
        register_blueprints()
        app.secret_key = str(uuid.uuid4())
        app.permanent_session_lifetime = timedelta(minutes=15)
        serve(
            app, url_scheme="https", host="0.0.0.0", port=8000, threads=15
        )  # Serve me the sky with a big slice of lemon
    except Exception as err:
        logthis.critical(
            f"JAWA failed to start: {err}. Check port availability."
        )
        raise


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
    # Log view
    from views import log_view

    app.register_blueprint(log_view.blueprint)
    # Resources (aka files) view
    from views import resource_view

    app.register_blueprint(resource_view.blueprint)
    # Template catalog, enable, and import view
    from views import template_view

    app.register_blueprint(template_view.blueprint)
    # Search view
    from views import search_view

    app.register_blueprint(search_view.blueprint)
    # Credential management view
    from views import credential_view

    app.register_blueprint(credential_view.blueprint)
    # Unified Automations view
    from views import automation_view

    app.register_blueprint(automation_view.blueprint)
    # Home, Dashboard and Login view
    from views import home_view

    app.register_blueprint(home_view.blueprint)


# --- Backward-compatibility 301 redirects ---
# Old webhook routes → new /automations/ routes


@app.route("/webhooks")
def _redir_webhooks():
    return redirect("/automations", code=301)


@app.route("/webhooks/jamf")
def _redir_jamf_list():
    return redirect("/automations/jamfpro", code=301)


@app.route("/webhooks/jamf/new")
def _redir_jamf_new():
    return redirect("/automations/jamfpro/new", code=301)


@app.route("/webhooks/jamf/edit")
def _redir_jamf_edit():
    name = request.args.get("name", "")
    return redirect(f"/automations/jamfpro/{name}/edit", code=301)


@app.route("/webhooks/okta")
def _redir_okta_list():
    return redirect("/automations/okta", code=301)


@app.route("/webhooks/okta/new")
def _redir_okta_new():
    return redirect("/automations/okta/new", code=301)


@app.route("/webhooks/custom")
def _redir_custom_list():
    return redirect("/automations/custom", code=301)


@app.route("/webhooks/custom/new")
def _redir_custom_new():
    return redirect("/automations/custom/new", code=301)


@app.route("/webhooks/custom/edit")
def _redir_custom_edit():
    name = request.args.get("name", "")
    return redirect(f"/automations/custom/{name}/edit", code=301)


@app.route("/cron")
def _redir_cron_list():
    return redirect("/automations/cron", code=301)


@app.route("/cron/new")
def _redir_cron_new():
    return redirect("/automations/cron/new", code=301)


@app.route("/cron/edit")
def _redir_cron_edit():
    name = request.args.get("name", "")
    return redirect(f"/automations/cron/{name}/edit", code=301)


@app.route("/cron/delete")
def _redir_cron_delete():
    name = request.args.get("target_job", "")
    return redirect(f"/automations/cron/{name}/delete", code=301)


@app.route("/webhooks/delete")
def _redir_webhook_delete():
    name = request.args.get("target_webhook", "")
    # Need to look up the tag to route properly
    from bin.data_store import get_webhook_by_name

    webhook = get_webhook_by_name(name)
    tag = webhook.get("tag", "custom") if webhook else "custom"
    return redirect(f"/automations/{tag}/{name}/delete", code=301)


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
        server_url = _strip_trailing_slash(request.form.get("address") or "")
        if not server_url:
            return redirect(url_for("setup"))
        jps_url = _strip_trailing_slash(request.form.get("jss-lock") or "")
        jps2_check = request.form.get("alternate-jamf")
        jps_url2 = _strip_trailing_slash(request.form.get("alternate") or "")
        timeout_raw = request.form.get("session_timeout_minutes", "")
        try:
            timeout_val = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_val = DEFAULT_SESSION_TIMEOUT
        # Clamp to the allowed ladder; never store an off-ladder value.
        session_timeout = _resolve_session_timeout(
            {"session_timeout_minutes": timeout_val}
        )
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
                    "session_timeout_minutes": session_timeout,
                }
                json.dump(server_json, outfile)
        elif os.path.isfile(server_json_file):
            with open(server_json_file, "w") as outfile:
                server_json = {
                    "jawa_address": server_url,
                    "jps_url": jps_url,
                    "alternate_jps": jps_url2,
                    "session_timeout_minutes": session_timeout,
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
        session_timeout = _resolve_session_timeout(server_json)
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
            session_timeout=session_timeout,
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
    logthis.warning(
        f"[{session.get('url')}] {session.get('username').title()} was a victim of a series of accidents, as are we all. (/error)"
    )
    return render_template(
        "error.html",
        username=session.get("username"),
        error=error_title,
        error_message=error_message,
    )


@app.errorhandler(404)
def page_not_found(e) -> Union[Response, str]:
    if "username" in session:
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} wandered off course  ({request.path}) - redirecting to /dashboard."
        )
        return redirect(url_for("home_view.dashboard"))
    logthis.info(
        f"An invalid path ({request.path}) was provided and no user is logged in.  Returning login page."
    )
    return load_home()


@app.errorhandler(500)
def internal_error(e) -> Union[Response, Tuple[str, int]]:
    logthis.exception(
        f"500 at {request.path} for "
        f"{session.get('username', 'anonymous')}"
    )
    if "username" in session:
        return (
            render_template(
                "error.html",
                username=session.get("username"),
                error="Something went wrong",
                error_message="An unexpected error occurred. "
                "The details have been logged.",
            ),
            500,
        )
    return load_home(), 500


@app.errorhandler(403)
def forbidden(e) -> Union[Response, Tuple[str, int]]:
    if "username" in session:
        return (
            render_template(
                "error.html",
                username=session.get("username"),
                error="Forbidden",
                error_message="You do not have access to that resource.",
            ),
            403,
        )
    return load_home(), 403


@app.errorhandler(405)
def method_not_allowed(e) -> Union[Response, Tuple[str, int]]:
    if "username" in session:
        return (
            render_template(
                "error.html",
                username=session.get("username"),
                error="Method not allowed",
                error_message="That action isn't allowed here.",
            ),
            405,
        )
    return load_home(), 405


if __name__ == "__main__":
    main()
