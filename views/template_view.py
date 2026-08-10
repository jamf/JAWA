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
import math
import os
import re
from typing import Any, Dict, List, Optional, Union

import requests
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
from werkzeug.utils import secure_filename

from bin import data_store, logger
from bin.data_store import get_jawa_address, get_webhook_schemas
from bin.tokens import get_token, validate_token
from bin.view_modifiers import response
from views._type_handlers.base import AutomationError
from views._type_handlers.jamf_handler import (
    USER_AGENT_STRING,
    VERIFY_SSL,
    XML,
    _build_auth_xml,
    _build_webhook_xml,
    _extract_auth_fields,
    _smart_group_info,
    validate_webhook_name,
)

# Reused, not re-implemented: the one-shot success flash has to behave
# identically on the template path and the create path, or the two drift
# on which context keys survive the redirect.
from views.automation_view import _flash_success

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


def _install_package(
    package: dict,
    jamf_id: Optional[str] = None,
    enabled: bool = True,
    auth_fields: Optional[Dict[str, str]] = None,
) -> None:
    """Install a .jawa.json workflow package into JAWA.

    ``jamf_id`` is the id of the webhook already created in Jamf Pro, or
    None when the admin cleared the registration box and wants a
    JAWA-local automation. Registered packages are filed under
    "jamfpro" so the automation carries its trigger the way the enable
    path's do -- filing an event-driven automation under "custom" is the
    B14 mistake, where the trigger becomes invisible and uneditable.
    """
    script = package["script"]
    safe_filename = secure_filename(script["filename"])
    script_path = os.path.join(SCRIPTS_DIR, safe_filename)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script["content"])
    os.chmod(script_path, 0o755)

    auth = auth_fields or {
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }
    entry = {
        "name": package["name"],
        "tag": "jamfpro" if jamf_id is not None else "custom",
        "url": session.get("url", ""),
        "jawa_admin": session.get("username", ""),
        "event": package["trigger"]["event"],
        "script": script_path,
        "description": package.get("description", ""),
        # Mirror what Jamf actually did: a smart-group event is created
        # disabled and does not fire until the admin picks a Smart Group,
        # so a flat True would make the stored record disagree with the
        # remote object.
        "enabled": enabled,
        **auth,
    }
    if jamf_id is not None:
        entry["jamf_id"] = jamf_id
    data_store.add_webhook(entry)

    logthis.info(
        f"Installed workflow package: {package['name']} "
        f"(script: {safe_filename}, jamf id: {jamf_id or 'not registered'})"
    )


CREDENTIAL_KEYS = ("server_url", "client_id", "client_secret")

# Every template token starts with this. Used as a tripwire: no computed
# replacement may reintroduce one, and none may survive substitution.
TOKEN_PREFIX = "__JAWA_"


def _numeric_literal(value: str, param: Dict[str, Any]) -> str:
    """Validate a numeric config value and render it as a literal.

    The one numeric token is written bare (no surrounding quotes), so
    whatever comes back lands in an expression position. Validation --
    not escaping -- is what keeps that safe.

    Deliberately lenient: surrounding whitespace is stripped, and a
    leading "+" or an exponent form ("1e5" -> 100000.0) is accepted,
    because those are things an admin plausibly types into a form field.
    Deliberately strict: the value must be ASCII, so a unicode digit
    cannot silently become a different number, and it must be finite.
    """
    label = param.get("label", param["key"])
    text = value.strip()
    if not text.isascii():
        raise AutomationError(
            "Invalid Configuration",
            f"{label} must be an ASCII number. Got: {value}",
        )
    try:
        number = int(text)
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            raise AutomationError(
                "Invalid Configuration",
                f"{label} must be a number. Got: {value}",
            )
        # float() happily accepts "inf", "nan", "Infinity" and "1e400".
        # repr(float("inf")) is the bare word inf, which is not a
        # builtin, so the deployed script would raise NameError on its
        # first trigger -- enable succeeds, the automation dies later.
        if not math.isfinite(number):
            raise AutomationError(
                "Invalid Configuration",
                f"{label} must be a finite number. Got: {value}",
            )
    return repr(number)


def _raw_literal(value: str, param: Dict[str, Any]) -> str:
    """Validate a raw (unquoted) config value and return it verbatim.

    The only raw token sits inside an XML <string> element held in a
    b\"\"\"...\"\"\" bytes literal, so the value is neither quoted Python
    nor escaped XML and has to be safe in both at once.
    """
    label = param.get("label", param["key"])
    # Structural characters: these would break out of the XML element or
    # out of the enclosing Python literal. "&" is here because a bare
    # ampersand is not well-formed XML, so the generated Apple profile
    # would be rejected at runtime.
    for char in ("<", ">", "&", '"', "'", "\\", "\n"):
        if char in value:
            raise AutomationError(
                "Invalid Configuration",
                f"{label} may not contain {char!r}.",
            )
    # A character blocklist alone is whack-a-mole, so this is a positive
    # rule over the whole control range rather than another list of
    # individual characters. NUL makes the deployed .py fail to
    # compile; the other C0/C1 codes either produce malformed XML or get
    # silently rewritten by the XML parser (CR becomes LF), which would
    # change the SSID an admin typed without telling them.
    for char in value:
        code = ord(char)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            raise AutomationError(
                "Invalid Configuration",
                f"{label} may not contain control characters. Got: {char!r}",
            )
    # That XML lives in a b\"\"\"...\"\"\" bytes literal, which cannot
    # hold a non-ASCII character at all -- substituting one makes the
    # deployed script fail to compile. Refuse at enable time rather
    # than shipping a script that cannot start.
    if not value.isascii():
        raise AutomationError(
            "Invalid Configuration",
            f"{label} must be ASCII only. Got: {value}",
        )
    return value


def _python_literal(value: str, param: Dict[str, Any]) -> str:
    """Render a config value as Python source text.

    The value is going into a .py file, not into HTML, so it must be a
    Python literal -- never HTML-escaped. The old engine ran
    markupsafe.escape() over form values before string-replacing them
    into script source, which turned every & in a Power Automate URL
    into &amp; (bug B13); the credential path did not escape at all, so
    a quote in a secret produced invalid Python. One function now
    serves both paths so they cannot diverge again.
    """
    if param.get("type") == "number":
        return _numeric_literal(value, param)
    if param.get("raw"):
        return _raw_literal(value, param)
    return repr(value)


def substitute_params(
    script_content: str,
    workflow: Dict[str, Any],
    form: Any,
    credentials: List[Dict[str, Any]],
    credential_index: str,
) -> str:
    """Fill every token in a template script.

    Values come from the selected credential set first, then the form.
    Every declared token must end up filled: an unfilled token used to
    leave the placeholder baked into the deployed script, so the
    automation failed at trigger time instead of at enable time.
    """
    cred: Dict[str, Any] = {}
    if credential_index and credentials:
        try:
            cred = credentials[int(credential_index)]
        except (ValueError, IndexError):
            cred = {}

    missing = []
    replacements: Dict[str, str] = {}
    for param in workflow.get("config_params", []):
        key = param["key"]
        value = ""
        if key in CREDENTIAL_KEYS and cred.get(key):
            value = cred[key]
        if not value:
            value = form.get(key, "")
        if not value:
            missing.append(param.get("label", key))
            continue
        replacement = _python_literal(str(value), param)
        # Belt and braces on top of the single pass below: a replacement
        # that itself contains a token would be a needle for nothing
        # now, but would come back the moment anyone reintroduces a
        # second pass over this text.
        if TOKEN_PREFIX in replacement:
            raise AutomationError(
                "Invalid Configuration",
                f"{param.get('label', key)} may not contain {TOKEN_PREFIX}.",
            )
        replacements[param["token"]] = replacement

    if missing:
        raise AutomationError(
            "Missing Configuration",
            "Fill in every configuration field before enabling this "
            "template. Missing: " + ", ".join(missing),
        )

    # Guarded rather than an early return: a workflow declaring no
    # config_params must still reach the survivor check below, or a
    # template carrying an undeclared token ships with the placeholder
    # baked in -- exactly the drift that check exists to catch.
    if replacements:
        # ONE pass over the source. Applying str.replace per param in a
        # loop re-scanned text that earlier params had already
        # substituted, so a value containing a later param's token got
        # rewritten from the inside -- breaking out of the Python string
        # literal it was supposed to be trapped in and turning a config
        # field into arbitrary code in the deployed script. re.sub with
        # a callback never reconsiders the text it has emitted, so a
        # substituted value can no longer influence any later
        # substitution.
        pattern = "|".join(
            re.escape(token)
            for token in sorted(replacements, key=len, reverse=True)
        )
        script_content = re.sub(
            pattern,
            lambda match: replacements[match.group(0)],
            script_content,
        )

    # Nothing may survive: a leftover token means the deployed script
    # would run against the literal string "__JAWA_...".
    if TOKEN_PREFIX in script_content:
        raise AutomationError(
            "Invalid Configuration",
            "The template script still contains unfilled placeholders "
            "after configuration. Please report this template.",
        )

    return script_content


def _write_script(name: str, content: str) -> str:
    """Write script content to a unique file and return the absolute path."""
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
    return dest_path


def _create_jamf_webhook(webhook_name: str, xml_data: str) -> str:
    """Create the webhook in Jamf Pro and return its id.

    Runs before any local write: if Jamf rejects the webhook there is
    no orphaned script on disk and no half-configured automation.
    """
    full_url = session["url"] + "/JSSResource/webhooks/id/0"
    try:
        resp = requests.post(
            full_url,
            headers={
                "Content-Type": XML,
                "Authorization": f"Bearer {session['token']}",
                "User-Agent": USER_AGENT_STRING,
            },
            data=xml_data,
            verify=VERIFY_SSL,
            timeout=30,
        )
    except requests.exceptions.Timeout as err:
        logthis.error(
            f"Timeout creating Jamf webhook {webhook_name}: {err}"
        )
        raise AutomationError(
            "Connection Timeout",
            f"Request to Jamf Pro timed out after 30 seconds. {err}",
        )
    except requests.exceptions.ConnectionError as err:
        logthis.error(
            f"Connection error creating Jamf webhook {webhook_name}: {err}"
        )
        raise AutomationError(
            "Connection Error",
            f"Could not connect to Jamf Pro. {err}",
        )
    except Exception as err:
        logthis.error(
            f"Unexpected error creating Jamf webhook {webhook_name}: {err}"
        )
        raise AutomationError(
            "API Error", f"Failed to create the webhook in Jamf Pro. {err}"
        )

    if resp.status_code == 409:
        logthis.error(
            f"Duplicate webhook name {webhook_name} in Jamf Pro (409)"
        )
        raise AutomationError(
            "Duplicate",
            f'The webhook name "{webhook_name}" already exists in your '
            f"Jamf Pro Server.",
        )
    if resp.status_code >= 400:
        logthis.error(
            f"Jamf API error creating webhook {webhook_name}: "
            f"HTTP {resp.status_code} - {resp.text}"
        )
        raise AutomationError(
            "API Error",
            f"Jamf Pro returned HTTP {resp.status_code}. Check the "
            f"API privileges on your account and try again.",
        )

    found = re.search("<id>(.*)</id>", resp.text)
    return found.group(1) if found else ""


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

    filename = package["script"]["filename"]
    safe = secure_filename(filename)
    if not safe or safe != filename:
        # secure_filename strips path separators / traversal; if the
        # result is empty or differs, the package tried to write
        # outside SCRIPTS_DIR (bug B7). Reject loudly, write nothing.
        return f"Unsafe script filename: {filename}"

    try:
        compile(package["script"]["content"], filename, "exec")
    except SyntaxError as err:
        # Only a parse gate -- deliberately NOT undefined-name
        # analysis. compile() catches truncated uploads and syntax
        # errors with no false positives, while a user's own script may
        # legitimately rely on a runtime global. Bundled scripts are
        # held to the stricter F821 bar by the catalog tests.
        return (
            f"Script does not parse as Python "
            f"(line {err.lineno}): {err.msg}"
        )
    except (ValueError, TypeError) as err:
        # e.g. embedded NUL bytes in the uploaded content.
        return f"Script content is not valid Python source: {err}"

    return None


# ---- Backward-compat redirects from /workflows ----


@blueprint.route("/workflows")
def workflows_redirect() -> Response:
    return redirect(url_for(CATALOG_ENDPOINT), code=301)


@blueprint.route("/workflows/<path:rest>")
def workflows_rest_redirect(rest: str) -> Response:
    # `rest` is a user-controlled path tail interpolated into the
    # redirect target. A value containing a backslash, a "//" run, or a
    # scheme colon could make the result protocol-relative / off-site
    # (open redirect, bug B8). Anything suspicious falls back to the
    # catalog rather than redirecting off-origin.
    if "\\" in rest or "//" in rest or ":" in rest:
        return redirect(url_for(CATALOG_ENDPOINT), code=301)
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
            event_categories=get_webhook_schemas()["categories"],
            # Passed, not hardcoded in Jinja: the template marks a param
            # required only when a credential set cannot supply it, and
            # duplicating the three key names there would drift.
            credential_keys=CREDENTIAL_KEYS,
        )

    # POST: enable the template
    try:
        webhook_name = request.form.get(
            "webhook_name", workflow["hook_name"]
        ).strip()
        # Shared with the jamfpro create path so the two cannot diverge:
        # the name goes into the XML body and into the callback URL.
        validate_webhook_name(webhook_name)
        if data_store.get_webhook_by_name(webhook_name):
            raise AutomationError(
                "Error", f'The name "{webhook_name}" is already in use.'
            )

        # trigger_event is null for any-event templates: the form asks.
        event = workflow.get("trigger_event") or request.form.get(
            "event", ""
        )
        if not event:
            raise AutomationError(
                "Error", "Choose the Jamf Pro event to listen for."
            )

        server_address = get_jawa_address()
        if not server_address:
            raise AutomationError(
                "Setup Required",
                "Configure your JAWA address and Jamf Pro server "
                "before enabling a template.",
                link="/setup",
                link_text="Go to Setup",
            )

        src_path = os.path.join(
            TEMPLATE_SCRIPTS_DIR, workflow["script_file"]
        )
        if not os.path.isfile(src_path):
            raise AutomationError(
                "Script not found",
                f"Script {workflow['script_file']} not found.",
            )
        with open(src_path, "r", encoding="utf-8") as f:
            script_content = f.read()

        # Fill every token BEFORE touching Jamf, so a missing field
        # fails before any remote state is created.
        script_content = substitute_params(
            script_content,
            workflow,
            request.form,
            credentials,
            request.form.get("credential_set", ""),
        )

        if not validate_token(session.get("expires")):
            get_token()

        notice, instructions, enablement, extra_xml = _smart_group_info(
            event
        )
        auth_xml = _build_auth_xml(request.form)
        (
            webhook_user,
            webhook_pass,
            webhook_apikey,
            extra_notice,
            custom_header,
        ) = _extract_auth_fields(request.form)

        xml_data = _build_webhook_xml(
            webhook_name,
            enablement,
            server_address,
            event,
            auth_xml,
            extra_xml,
        )
        jamf_id = _create_jamf_webhook(webhook_name, xml_data)
    except AutomationError as err:
        return redirect(
            url_for(
                "error",
                error=err.title,
                error_message=err.message,
            )
        )

    # Jamf accepted it: only now write anything locally.
    dest_path = _write_script(webhook_name, script_content)
    data_store.add_webhook(
        {
            "name": webhook_name,
            "tag": "jamfpro",
            "url": session.get("url", ""),
            "jawa_admin": session.get("username", ""),
            "event": event,
            "script": dest_path,
            "description": workflow.get("description", ""),
            # Mirror what Jamf actually did, not what we asked for: a
            # smart-group event is created with enablement "false" and
            # does not fire until the admin picks a Smart Group. Writing
            # a flat True would make the stored record disagree with the
            # remote object the notice below warns about.
            "enabled": enablement == "true",
            "jamf_id": jamf_id,
            "webhook_username": webhook_user,
            "webhook_password": webhook_pass,
            "api_key": webhook_apikey,
        }
    )

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} "
        f"enabled template: {webhook_name} "
        f"(script: {os.path.basename(dest_path)}, jamf id: {jamf_id})"
    )

    # The create path's own one-shot flash + PRG, so the notices survive
    # the redirect. A smart-group event is created DISABLED in Jamf Pro,
    # so reporting a bare "Enabled" for those three templates would
    # leave the user believing the automation is already live.
    return _flash_success(
        success_msg=f"Enabled template: {webhook_name}",
        new_link=f"{session.get('url')}/webhooks.html?id={jamf_id}&o=r",
        new_here=webhook_name,
        smart_group_notice=notice,
        smart_group_instructions=instructions,
        extra_notice=extra_notice,
        custom_header=custom_header,
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

    # Default-on, and read as "absent means cleared": an unchecked box
    # posts nothing at all. These packages are predicated on Jamf Pro
    # events, so registering the webhook in Jamf -- the coupling the
    # regular create path gives -- is the expected outcome, not an extra
    # step the admin has to discover.
    if not request.form.get("create_in_jamf"):
        _install_package(package)
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} "
            f"imported template: {package['name']} (JAWA-local)"
        )
        return _flash_success(
            success_msg=f"Installed template: {package['name']}"
        )

    webhook_name = package["name"]
    event = package["trigger"]["event"]
    try:
        # Shared with the create and enable paths so the three cannot
        # diverge: the name goes into the XML body and into the callback
        # URL Jamf Pro calls. Re-framed on the way out because this form
        # has no name field -- the name comes from the package, so
        # "rename it" is not advice the admin can act on here.
        try:
            validate_webhook_name(webhook_name)
        except AutomationError as err:
            raise AutomationError(
                ERROR_INVALID_PKG,
                f'The package name "{webhook_name}" cannot be used as a '
                f"Jamf Pro webhook. {err.message} Fix the name in the "
                f"package file, or clear the Jamf Pro box to install the "
                f"script locally only.",
            )
        if data_store.get_webhook_by_name(webhook_name):
            raise AutomationError(
                "Error", f'The name "{webhook_name}" is already in use.'
            )

        server_address = get_jawa_address()
        if not server_address:
            raise AutomationError(
                "Setup Required",
                "Configure your JAWA address and Jamf Pro server "
                "before importing a template into Jamf Pro.",
                link="/setup",
                link_text="Go to Setup",
            )

        if not validate_token(session.get("expires")):
            get_token()

        notice, instructions, enablement, extra_xml = _smart_group_info(
            event
        )
        # The helpers rather than a hardcoded NONE + "null" x3: the
        # import form carries no auth fields today, so both reduce to
        # unauthenticated -- but going through them keeps the XML JAWA
        # sends and the credentials JAWA stores derived from one place.
        # Hardcoding the pair is how they drift into telling Jamf NONE
        # while storing something the receiver then rejects (B14).
        auth_xml = _build_auth_xml(request.form)
        (
            webhook_user,
            webhook_pass,
            webhook_apikey,
            _extra_notice,
            _custom_header,
        ) = _extract_auth_fields(request.form)
        xml_data = _build_webhook_xml(
            webhook_name,
            enablement,
            server_address,
            event,
            auth_xml,
            extra_xml,
        )
        jamf_id = _create_jamf_webhook(webhook_name, xml_data)
    except AutomationError as err:
        return redirect(
            url_for(
                "error",
                error=err.title,
                error_message=err.message,
            )
        )

    # Jamf accepted it: only now write anything locally, so a rejection
    # leaves no orphaned script on disk and no half-configured
    # automation.
    _install_package(
        package,
        jamf_id=jamf_id,
        enabled=enablement == "true",
        auth_fields={
            "webhook_username": webhook_user,
            "webhook_password": webhook_pass,
            "api_key": webhook_apikey,
        },
    )
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} "
        f"imported template: {package['name']} (jamf id: {jamf_id})"
    )
    return _flash_success(
        success_msg=f"Installed template: {package['name']}",
        new_link=f"{session.get('url')}/webhooks.html?id={jamf_id}&o=r",
        new_here=webhook_name,
        smart_group_notice=notice,
        smart_group_instructions=instructions,
    )
