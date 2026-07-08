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

import json
import os
from typing import Any, Dict, List, Union

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from markupsafe import escape

from bin import data_store, logger
from bin.view_modifiers import response

blueprint = Blueprint(
    "template_view",
    __name__,
    template_folder="../templates",
)

logthis = logger.setup_child_logger("jawa", "template_view")

ERROR_TITLE = "Session Timed Out"
ERROR_MSG_SIGN_IN = "Please sign in again"
ERROR_INVALID_PKG = "Invalid Package"
LOGOUT_ENDPOINT = "home_view.logout"
CATALOG_ENDPOINT = "template_view.catalog"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_CONFIG = os.path.join(
    BASE_DIR, "data", "workflows", "workflow_config.json"
)
TEMPLATE_SCRIPTS_DIR = os.path.join(BASE_DIR, "data", "workflows", "scripts")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
WEBHOOKS_FILE = os.path.join(BASE_DIR, "data", "webhooks.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "data", "credentials.json")


def _load_config() -> list:
    """Load the workflow configuration file."""
    try:
        with open(WORKFLOW_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logthis.warning("Could not load workflow_config.json")
        return []


def _get_workflow_by_slug(slug: str) -> Union[Dict[str, Any], None]:
    """Look up a workflow by its URL slug."""
    workflows = _load_config()
    for wf in workflows:
        if wf.get("slug") == slug:
            return wf
    return None


def _load_credentials() -> List[Dict[str, Any]]:
    """Load saved credential sets."""
    if not os.path.isfile(CREDENTIALS_FILE):
        return []
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _install_package(package: dict) -> None:
    """Install a .jawa.json workflow package into JAWA."""
    script = package["script"]
    script_path = os.path.join(SCRIPTS_DIR, script["filename"])
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script["content"])
    os.chmod(script_path, 0o755)

    data_store.add_webhook(
        {
            "name": package["name"],
            "tag": "custom",
            "event": package["trigger"]["event"],
            "script": script["filename"],
            "enabled": True,
            "webhook_username": "null",
            "webhook_password": "null",
            "api_key": "null",
        }
    )

    logthis.info(
        f"Installed workflow package: {package['name']} "
        f"(script: {script['filename']})"
    )


def _apply_credentials(
    script_content: str,
    workflow: dict,
    credential_index: str,
    credentials: list,
) -> str:
    """Substitute credential placeholders in script content."""
    if not credential_index or not credentials:
        return script_content
    try:
        cred = credentials[int(credential_index)]
    except (ValueError, IndexError):
        return script_content

    cred_keys = ("server_url", "client_id", "client_secret")
    for param in workflow.get("config_params", []):
        key = param.get("key", "")
        if key in cred_keys and cred.get(key):
            script_content = script_content.replace(
                param["placeholder"], cred[key]
            )
    return script_content


def _apply_form_params(script_content: str, workflow: dict) -> str:
    """Substitute remaining form-supplied placeholders."""
    for param in workflow.get("config_params", []):
        key = param.get("key", "")
        form_value = request.form.get(key, "")
        if form_value:
            form_value = str(escape(form_value))
            script_content = script_content.replace(
                param["placeholder"], form_value
            )
    return script_content


def _write_script(name: str, content: str) -> str:
    """Write script content to a unique file and return the filename."""
    safe_name = name.replace(" ", "_").replace("/", "_").lower()
    dest_filename = f"{safe_name}.py"
    dest_path = os.path.join(SCRIPTS_DIR, dest_filename)

    counter = 1
    while os.path.isfile(dest_path):
        dest_filename = f"{safe_name}_{counter}.py"
        dest_path = os.path.join(SCRIPTS_DIR, dest_filename)
        counter += 1

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(dest_path, 0o755)
    return dest_filename


def _validate_package(package: dict) -> Union[str, None]:
    """Validate a .jawa.json package. Returns error message or None."""
    for field in ("name", "trigger", "script"):
        if field not in package:
            return f"Missing required field: {field}"

    if (
        "filename" not in package["script"]
        or "content" not in package["script"]
    ):
        return "Script must have filename and content."

    if "event" not in package["trigger"]:
        return "Trigger must have an event field."

    return None


# ---- Backward-compat redirects from /workflows ----


@blueprint.route("/workflows")
def workflows_redirect() -> Response:
    return redirect(url_for(CATALOG_ENDPOINT), code=301)


@blueprint.route("/workflows/<path:rest>")
def workflows_rest_redirect(rest: str) -> Response:
    return redirect(f"/templates/{rest}", code=301)


# ---- Template routes ----


@blueprint.route("/templates")
@response(template_file="workflows/catalog.html")
def catalog() -> Union[Response, Dict[str, Any]]:
    """Template catalog page showing all bundled templates."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )
    workflows = _load_config()
    workflows.sort(key=lambda w: w.get("order", 99))

    categories: Dict[str, list] = {}
    for wf in workflows:
        cat = wf.get("category", "other")
        categories.setdefault(cat, []).append(wf)

    return {
        "username": session.get("username"),
        "workflows": workflows,
        "categories": categories,
    }


@blueprint.route("/templates/<slug>")
@response(template_file="workflows/detail.html")
def detail(slug: str) -> Union[Response, Dict[str, Any]]:
    """Template detail page with description and script preview."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )
    slug = str(escape(slug))
    workflow = _get_workflow_by_slug(slug)
    if not workflow:
        return redirect(url_for(CATALOG_ENDPOINT))

    script_content = ""
    script_path = os.path.join(TEMPLATE_SCRIPTS_DIR, workflow["script_file"])
    if os.path.isfile(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script_content = f.read()

    credentials = _load_credentials()

    return {
        "username": session.get("username"),
        "workflow": workflow,
        "script_content": script_content,
        "credentials": credentials,
    }


@blueprint.route("/templates/<slug>/script")
def download_script(slug: str) -> Union[Response, str]:
    """Download the template script file."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )
    slug = str(escape(slug))
    workflow = _get_workflow_by_slug(slug)
    if not workflow:
        return redirect(url_for(CATALOG_ENDPOINT))

    script_path = os.path.join(TEMPLATE_SCRIPTS_DIR, workflow["script_file"])
    if not os.path.isfile(script_path):
        return redirect(
            url_for(
                "error",
                error="Script not found",
                error_message=f"Script {workflow['script_file']} not found.",
            )
        )

    return send_file(
        script_path,
        as_attachment=True,
        download_name=workflow["script_file"],
    )


@blueprint.route("/templates/<slug>/enable", methods=["GET", "POST"])
def enable_template(slug: str) -> Union[Response, str]:
    """Enable a template: configure and install as a webhook."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    slug = str(escape(slug))
    workflow = _get_workflow_by_slug(slug)
    if not workflow:
        return redirect(url_for(CATALOG_ENDPOINT))

    credentials = _load_credentials()

    if request.method == "GET":
        return render_template(
            "workflows/enable.html",
            username=session.get("username"),
            workflow=workflow,
            credentials=credentials,
        )

    # POST: enable the template
    webhook_name = str(
        escape(request.form.get("webhook_name", workflow["title"]))
    )

    src_path = os.path.join(TEMPLATE_SCRIPTS_DIR, workflow["script_file"])
    if not os.path.isfile(src_path):
        return redirect(
            url_for(
                "error",
                error="Script not found",
                error_message=f"Script {workflow['script_file']} not found.",
            )
        )

    with open(src_path, "r", encoding="utf-8") as f:
        script_content = f.read()

    script_content = _apply_credentials(
        script_content,
        workflow,
        request.form.get("credential_set", ""),
        credentials,
    )
    script_content = _apply_form_params(script_content, workflow)
    dest_filename = _write_script(webhook_name, script_content)

    data_store.add_webhook(
        {
            "name": webhook_name,
            "tag": "custom",
            "url": session.get("url", ""),
            "event": workflow.get("trigger_event", ""),
            "script": dest_filename,
            "description": workflow.get("description", ""),
            "enabled": True,
            "webhook_username": "null",
            "webhook_password": "null",
            "api_key": "null",
        }
    )

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} "
        f"enabled template: {webhook_name} (script: {dest_filename})"
    )

    return redirect(
        url_for(
            "success",
            success_msg=f"Enabled template: {webhook_name}",
        )
    )


@blueprint.route("/templates/import", methods=["GET", "POST"])
@response(template_file="workflows/import.html")
def import_template() -> Union[Response, Dict[str, Any]]:
    """Upload a .jawa.json package to install a new template."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    if request.method != "POST":
        return {"username": session.get("username")}

    uploaded = request.files.get("package")
    if not uploaded or not uploaded.filename.endswith(".jawa.json"):
        return redirect(
            url_for(
                "error",
                error="Invalid File",
                error_message="Please upload a .jawa.json file.",
            )
        )

    try:
        package = json.load(uploaded)
    except json.JSONDecodeError:
        return redirect(
            url_for(
                "error",
                error="Invalid JSON",
                error_message="The uploaded file is not valid JSON.",
            )
        )

    validation_error = _validate_package(package)
    if validation_error:
        return redirect(
            url_for(
                "error",
                error=ERROR_INVALID_PKG,
                error_message=validation_error,
            )
        )

    _install_package(package)
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} "
        f"imported template: {package['name']}"
    )
    return redirect(
        url_for(
            "success",
            success_msg=f"Installed template: {package['name']}",
        )
    )
