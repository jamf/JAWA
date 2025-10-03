# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2025 Jamf.  All rights reserved.
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
from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import json
from markupsafe import escape
import os
from typing import Any, Dict, Union

from werkzeug.utils import secure_filename

from bin.view_modifiers import response
from bin import logger

ERROR_TITLE = "Session Timed Out"
LOGOUT_ENDPOINT = "home_view.logout"
ERROR_MESSAGE = "Please sign in again"

logthis = logger.setup_child_logger("jawa", __name__)

blueprint = Blueprint("custom_webhook", __name__, template_folder="templates")

server_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "server.json")
)
okta_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "okta_json.json")
)
okta_verification_file = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "bin", "okta_verification.py"
    )
)
webhooks_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "webhooks.json")
)
scripts_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)


@blueprint.route("/webhooks/custom", methods=["GET", "POST"])
@response(template_file="webhooks/custom/home.html")
def custom_webhook() -> Union[Response, Dict[str, Any]]:
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MESSAGE,
            )
        )
    with open(webhooks_file, "r") as fin:
        webhooks_json = json.load(fin)
    custom_webhooks_list = []
    for each_webhook in webhooks_json:
        data = defaultdict(lambda: "MISSING", each_webhook)
        tag = data["tag"]
        if tag == "custom":
            custom_webhooks_list.append(each_webhook)

    return {
        "username": session.get("username"),
        "custom_list": custom_webhooks_list,
    }


@blueprint.route("/webhooks/custom/edit", methods=["GET", "POST"])
@response(template_file="webhooks/custom/edit.html")
def edit_webhook() -> Union[Response, Dict[str, Any]]:
    session_check = validate_session()
    if session_check:
        return session_check
    name = request.args.get("name")
    check_for_name, name, webhooks_json = check_for_dupes(name)
    if not check_for_name:
        logthis.info(f"JAWA is not aware of any custom webhook named {name}")
        return redirect(url_for("custom_webhook.custom_webhook"))
    if request.method == "POST":
        result = process_edit_webhook(
            request.form, request.files, session, name, webhooks_json
        )
        if "redirect" in result:
            return redirect(result["redirect"])
        return result
    webhook_info = [
        each_webhook
        for each_webhook in webhooks_json
        if each_webhook["name"] == name
    ]
    return {
        "username": session.get("username"),
        "webhook_name": name,
        "webhook_info": webhook_info,
    }


@blueprint.route("/webhooks/custom/new", methods=["GET", "POST"])
def new_webhook() -> Union[Response, Dict[str, Any], str]:
    session_check = validate_session()
    if session_check:
        return session_check
    if request.method == "POST":
        result = process_new_webhook(request.form, request.files, session)
        if not result:
            return render_template(
                "webhooks/custom/new.html", username=session.get("username")
            )
        if "template" in result:
            return render_template(
                result["template"],
                webhooks=result["webhooks"],
                success_msg=result["success_msg"],
                extra_notice=result["extra_notice"],
                custom_header=result["custom_header"],
                username=result["username"],
            )
        return result
    return render_template(
        "webhooks/custom/new.html", username=session.get("username")
    )


def check_for_dupes(name):
    if name:
        name = escape(name)
    logthis.info(f"Checking for custom webhook '{name}'")
    with open(webhooks_file) as fin:
        webhooks_json = json.load(fin)
    check_for_name = [
        True for each_webhook in webhooks_json if each_webhook["name"] == name
    ]
    logthis.info(f"Name exists? {check_for_name}")
    return check_for_name, name, webhooks_json


def validate_session():
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MESSAGE,
            )
        )
    return None


def get_form_value(form, key, default="null"):
    value = form.get(key)
    return value if value else default


def handle_file_upload(file, custom_name, scripts_dir):
    if not file:
        return None
    owd = os.getcwd()
    if not os.path.isdir(scripts_dir):
        os.mkdir(scripts_dir)
    os.chdir(scripts_dir)
    if " " in file.filename:
        file.filename = file.filename.replace(" ", "-")
    new_filename = f"{custom_name}-{file.filename}"
    file.save(secure_filename(new_filename))
    new_filename = os.path.join(scripts_dir, new_filename)
    os.chmod(new_filename, mode=0o0755)
    os.chdir(owd)
    return new_filename


def process_new_webhook(form, files, session):
    new_custom_name = form.get("custom_name")
    description = form.get("description")
    output = form.get("output")
    if not new_custom_name:
        return None
    with open(webhooks_file, "r") as json_file:
        webhooks_json = json.load(json_file)
    if any(each.get("name") == new_custom_name for each in webhooks_json):
        error_message = "Name already exists!"
        logthis.info(f"Could not create new webhook. Message: {error_message}")
        return {
            "error": error_message,
            "username": session.get("username"),
            "name": new_custom_name,
            "description": description,
        }
    new_filename = handle_file_upload(
        files.get("new_file"), new_custom_name, scripts_dir
    )
    new_webhook_user = get_form_value(form, "basic_username")
    new_webhook_pass = get_form_value(form, "new-password")
    if form.get("custom"):
        api_key = get_form_value(form, "api_key")
        extra_notice = (
            "Use the following in your request headers for authentication: "
        )
        custom_header = {"x-api-key": f"{api_key}"}
    else:
        extra_notice = None
        custom_header = None
        api_key = "null"
    webhooks_json.append(
        {
            "url": str(session["url"]),
            "jawa_admin": str(session["username"]),
            "name": new_custom_name,
            "webhook_username": new_webhook_user,
            "webhook_password": new_webhook_pass,
            "api_key": api_key,
            "script": new_filename,
            "description": description,
            "tag": "custom",
            "output": output,
        }
    )
    with open(webhooks_file, "w") as outfile:
        json.dump(webhooks_json, outfile, indent=4)
    success_msg = "New webhook created:"
    return {
        "template": "success.html",
        "webhooks": "success",
        "success_msg": success_msg,
        "extra_notice": extra_notice,
        "custom_header": custom_header,
        "username": str(escape(session["username"])),
    }


def update_webhook(each_webhook, form, files, name):
    output = form.get("output")
    new_custom_name = get_form_value(form, "custom_name", name)
    description = form.get("description")
    new_webhook_user = (
        get_form_value(form, "basic_username") if form.get("basic") else "null"
    )
    new_webhook_pass = (
        get_form_value(form, "new-password") if form.get("basic") else "null"
    )
    if form.get("custom"):
        new_webhook_apikey = get_form_value(form, "api_key")
        extra_notice = (
            "Use the following in your request headers for authentication: "
        )
        custom_header = {"x-api-key": f"{new_webhook_apikey}"}
    else:
        new_webhook_apikey = "null"
        extra_notice = None
        custom_header = None
    each_webhook["webhook_username"] = new_webhook_user
    each_webhook["webhook_password"] = new_webhook_pass
    each_webhook["api_key"] = new_webhook_apikey
    new_filename = handle_file_upload(
        files.get("new_file"), new_custom_name, scripts_dir
    )
    if new_filename:
        each_webhook["script"] = new_filename
    each_webhook["name"] = new_custom_name
    if description:
        each_webhook["description"] = description
    each_webhook["output"] = output
    return extra_notice, custom_header, new_custom_name


def process_edit_webhook(form, files, session, name, webhooks_json):
    button_choice = form.get("button_choice")
    if button_choice == "Delete":
        logthis.info(
            f"{session.get('username')} is considering deleting a custom webhook ({name})..."
        )
        return {
            "redirect": url_for("webhooks.delete_webhook", target_webhook=name)
        }
    for each_webhook in webhooks_json:
        if each_webhook["name"] == name:
            logthis.info(
                f"{session.get('username')} is editing a custom webhook ({name})..."
            )
            extra_notice, custom_header, new_custom_name = update_webhook(
                each_webhook, form, files, name
            )
            with open(webhooks_file, "w") as fout:
                json.dump(webhooks_json, fout, indent=4)
            webhook_info = [each_webhook]
            return {
                "webhooks": "success",
                "success_msg": f"Edited custom webhook {new_custom_name}.",
                "username": session.get("username"),
                "webhook_info": webhook_info,
                "webhook_name": new_custom_name,
                "description": each_webhook.get("description"),
                "extra_notice": extra_notice,
                "custom_header": custom_header,
            }
    webhook_info = [
        each_webhook
        for each_webhook in webhooks_json
        if each_webhook["name"] == name
    ]
    return {
        "username": session.get("username"),
        "webhook_name": name,
        "webhook_info": webhook_info,
    }
