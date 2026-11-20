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

import copy
import json
import os
import re
from typing import Any, Dict, Optional, Tuple, Union

from flask import (
    Blueprint,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape

from bin import data_store, logger
from bin.auth import login_required
from bin.data_store import (
    add_cron,
    add_webhook,
    clear_tap_cooldowns,
    clear_runs,
    rename_runs,
    get_all_crons,
    get_all_webhooks,
    get_cron_by_name,
    get_webhook_by_name,
    get_jawa_address,
    get_runs,
    get_webhooks_by_tag,
    save_all_webhooks,
    remove_cron,
    remove_webhook,
    webhook_name_exists,
    cron_name_exists,
)
from views._type_handlers import HANDLERS, get_handler
from views._type_handlers.base import AutomationError, validate_webhook_name
from views._type_handlers.jamf_handler import SMART_GROUP_EVENTS, jamf_status
from webhook import jawa_receiver

logthis = logger.setup_child_logger("jawa", "automation_view")

blueprint = Blueprint("automations", __name__)

LIST_TYPE_ENDPOINT = "automations.list_type"


def _get_session_data() -> dict:
    return {
        "url": session.get("url"),
        "username": session.get("username"),
        "token": session.get("token"),
        "expires": session.get("expires"),
    }


def _flash_success(**ctx: Any) -> Response:
    """Stash success context in a one-shot session flash and redirect to
    /success (Post-Redirect-Get). Keeps the POST from being the terminal
    history entry, so browser-back cannot re-issue it. Values must be
    JSON-serializable (strings/None); this mirrors the login_retry flash
    pattern in home_view."""
    session["success_ctx"] = {k: v for k, v in ctx.items() if v is not None}
    return redirect(url_for("success"))


def _error_page(
    title: str, message: str, link: str = None, link_text: str = None
) -> str:
    return render_template(
        "error.html",
        error=title,
        error_message=message,
        link=link,
        link_text=link_text,
        username=session.get("username"),
    )


# --- List routes ---


@blueprint.route("/automations")
@login_required
def list_all() -> Union[Response, str]:
    """List all automations across all types."""
    logthis.debug(
        f"[{session.get('url')}] {session.get('username')} viewed /automations"
    )
    all_webhooks = get_all_webhooks()
    all_crons = get_all_crons()
    categorized = {}
    for tag, handler in HANDLERS.items():
        if tag == "cron":
            items = all_crons
        else:
            items = [w for w in all_webhooks if w.get("tag") == tag]
        categorized[tag] = {"handler": handler, "items": items}

    return render_template(
        "automations/list_all.html",
        categorized=categorized,
        handlers=HANDLERS,
    )


@blueprint.route("/automations/new")
@login_required
def choose_type() -> str:
    """Pick which kind of automation to create."""
    return render_template("automations/choose.html", handlers=HANDLERS)


@blueprint.route("/automations/<auto_type>")
@login_required
def list_type(auto_type: str) -> Union[Response, str]:
    """List automations for a specific type."""
    handler = get_handler(auto_type)
    if not handler:
        abort(404)
    logthis.debug(
        f"[{session.get('url')}] {session.get('username')} "
        f"viewed /automations/{auto_type}"
    )
    if auto_type == "cron":
        items = get_all_crons()
    else:
        items = get_webhooks_by_tag(auto_type)

    return render_template(
        "automations/list.html",
        handler=handler,
        auto_type=auto_type,
        items=items,
    )


# --- Create ---


@blueprint.route("/automations/<auto_type>/new", methods=["GET", "POST"])
@login_required
def create(auto_type: str) -> Union[Response, str]:
    handler = get_handler(auto_type)
    if not handler:
        abort(404)

    session_data = _get_session_data()

    if request.method == "GET":
        ctx = handler.get_create_context(session_data)
        return render_template(
            "automations/create.html",
            handler=handler,
            auto_type=auto_type,
            **ctx,
        )

    # POST — process creation
    try:
        # Check for duplicate name
        name = _extract_name(auto_type, request.form)
        if name:
            if auto_type == "cron":
                exists = cron_name_exists(name)
            else:
                exists = webhook_name_exists(name)
            if exists:
                raise AutomationError("Error", "Name already exists!")

        result = handler.process_create(
            request.form, request.files, session_data
        )
    except AutomationError as err:
        return _error_page(err.title, err.message, err.link, err.link_text)
    except ValueError as err:
        # e.g. save_script rejecting an upload with no shebang.
        return _error_page("Invalid script", str(err))

    # Persist the entry
    entry = result.get("entry")
    if entry:
        if auto_type == "cron":
            add_cron(entry)
        else:
            add_webhook(entry)

    return _flash_success(
        auto_type=auto_type,
        success_msg=result.get("success_msg", "Created successfully."),
        new_link=result.get("new_link"),
        new_here=result.get("new_here"),
        smart_group_notice=result.get("smart_group_notice"),
        smart_group_instructions=result.get("smart_group_instructions"),
        extra_notice=result.get("extra_notice"),
        custom_header=result.get("custom_header"),
        webhook_url=result.get("webhook_url"),
        webhook_url_missing=result.get("webhook_url_missing"),
    )


# --- Detail ---


@blueprint.route("/automations/<auto_type>/<name>")
@login_required
def detail(auto_type: str, name: str) -> Union[Response, str]:
    handler = get_handler(auto_type)
    if not handler:
        abort(404)

    name = str(escape(name))
    if auto_type == "cron":
        automation = get_cron_by_name(name)
    else:
        automation = get_webhook_by_name(name)

    if not automation:
        logthis.info(f"Automation '{name}' not found")
        return redirect(url_for(LIST_TYPE_ENDPOINT, auto_type=auto_type))

    detail_fields = handler.get_detail_fields(automation)
    jawa_address = get_jawa_address()
    copyable = set(handler.copyable_labels)
    if auto_type == "custom" and not jawa_address:
        copyable.discard("Webhook URL")

    jamf_state = None
    if auto_type == "jamfpro":
        jamf_state = jamf_status(automation, _get_session_data())
        _remember_jamf_enabled(automation, jamf_state)

    webclip = None
    if auto_type == "tap":
        from views._type_handlers.tap_handler import webclip_preview

        webclip = webclip_preview(automation)

    return render_template(
        "automations/detail.html",
        handler=handler,
        webclip=webclip,
        auto_type=auto_type,
        automation=automation,
        detail_fields=detail_fields,
        copyable_labels=copyable,
        jawa_address=jawa_address,
        script=_read_script(automation.get("script")),
        runs=_masked_runs(name),
        jamf_state=jamf_state,
        sample=sample_form(automation) if auto_type == "jamfpro" else None,
        smart_group_events=SMART_GROUP_EVENTS,
    )


# --- Script view ---

SCRIPT_VIEW_LIMIT = 200 * 1024
SECRET_WORDS = r"(?:secret|password|token|api_?key)"
_SECRET_NAME = rf"[\w.\-]*{SECRET_WORDS}[\w.\-]*"
# name = "value", name: "value", "name": "value" and NAME='value'.
_QUOTED_SECRET = re.compile(
    rf"""(?P<head>(?P<q1>["']?)\b{_SECRET_NAME}(?P=q1)\s*[=:]\s*)"""
    r"""(?P<q>["'])(?:(?!(?P=q)).)*(?P=q)""",
    re.IGNORECASE,
)
# Shell style NAME=value with no spaces and no command substitution.
_BARE_SECRET = re.compile(
    rf"""^(?P<head>\s*(?:export\s+)?{_SECRET_NAME}=)(?P<value>[^\s"'$`()#]+)""",
    re.IGNORECASE | re.MULTILINE,
)


def mask_secrets(text: str) -> str:
    """Replace values assigned to secret-looking names with asterisks."""
    text = _QUOTED_SECRET.sub(
        lambda m: f"{m.group('head')}{m.group('q')}********{m.group('q')}",
        text,
    )
    return _BARE_SECRET.sub(lambda m: f"{m.group('head')}********", text)


def _masked_runs(name: str) -> list:
    """Run history with secrets masked in the output, like the script view."""
    return [
        {**run, "output_head": mask_secrets(run.get("output_head") or "")}
        for run in get_runs(name)
    ]


def _inside_scripts_dir(path: str) -> bool:
    root = os.path.realpath(data_store.SCRIPTS_DIR)
    target = os.path.realpath(path)
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:
        return False


def _read_script(path: Optional[str]) -> Dict[str, Any]:
    """What the detail page shows for the automation's script.

    Only files under the scripts folder are read, and secrets are masked
    before the text leaves this function.
    """
    if not path:
        return {"status": "none"}
    if not _inside_scripts_dir(path):
        return {"status": "outside", "path": path}
    if not os.path.isfile(path):
        return {"status": "missing", "path": path}
    try:
        with open(path, "rb") as handle:
            raw = handle.read(SCRIPT_VIEW_LIMIT + 1)
    except OSError as err:
        logthis.warning(f"Could not read script {path}: {err}")
        return {"status": "missing", "path": path}
    truncated = len(raw) > SCRIPT_VIEW_LIMIT
    text = mask_secrets(raw[:SCRIPT_VIEW_LIMIT].decode("utf-8", "replace"))
    return {
        "status": "ok",
        "path": path,
        "filename": os.path.basename(path),
        "content": text,
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "truncated": truncated,
        "language": "python" if path.endswith(".py") else "plaintext",
    }


def _remember_jamf_enabled(automation: Dict, state: Dict) -> None:
    """Keep the dashboard's "Off in Jamf Pro" marker in step with Jamf Pro."""
    if state.get("state") not in ("enabled", "disabled"):
        return
    enabled = state["state"] == "enabled"
    if automation.get("jamf_enabled") is enabled:
        return
    webhooks = get_all_webhooks()
    data_store.update_webhook_in_list(
        webhooks, automation["name"], {"jamf_enabled": enabled}
    )
    save_all_webhooks(webhooks)


# --- Send a sample event ---

SAMPLE_UNSUPPORTED = (
    "Sample events can only be sent to Jamf Pro and custom automations."
)

# Device keys an admin can set on a Jamf Pro sample event, when the
# event's sample has them. The bundled ids are made up, and a script
# that calls Jamf Pro with one acts on whatever real device has it.
SAMPLE_DEVICE_FIELDS = (
    ("jssID", "Jamf Pro ID"),
    ("serialNumber", "Serial number"),
    ("deviceName", "Device name"),
    ("udid", "UDID"),
)
SAMPLE_VALUE_LIMIT = 200


class SampleInputError(ValueError):
    """The admin's sample payload or device fields cannot be used."""

    def __init__(self, message: str, title: str = "Invalid device") -> None:
        super().__init__(message)
        self.title = title


def _jamf_sample(automation: Dict) -> Optional[Dict]:
    """The event's bundled sample with the remembered device applied."""
    example = data_store.get_webhook_schemas()["examples"].get(
        automation.get("event", "")
    )
    if not example:
        return None
    payload = copy.deepcopy(example)
    event = payload.get("event")
    if isinstance(event, dict):
        for key, value in (automation.get("sample_device") or {}).items():
            if key in event:
                event[key] = value
    return payload


def sample_form(automation: Dict) -> Optional[Dict]:
    """Device fields and payload JSON for a Jamf Pro sample event form."""
    payload = _jamf_sample(automation)
    if payload is None:
        return None
    event = payload.get("event")
    event = event if isinstance(event, dict) else {}
    fields = [
        {"key": key, "label": label, "value": event[key]}
        for key, label in SAMPLE_DEVICE_FIELDS
        if key in event
    ]
    return {"fields": fields, "json": json.dumps(payload, indent=2)}


def _apply_device_fields(payload: Dict, form: Any) -> Dict:
    """Write the posted device fields into payload["event"].

    Returns the values applied, for remembering. A blank field keeps the
    payload's value. Raises SampleInputError on a bad value.
    """
    event = payload.get("event")
    if not isinstance(event, dict):
        return {}
    applied = {}
    for key, label in SAMPLE_DEVICE_FIELDS:
        raw = (form.get(f"device_{key}") or "").strip()
        if not raw or key not in event:
            continue
        if len(raw) > SAMPLE_VALUE_LIMIT:
            raise SampleInputError(f"{label} is too long.")
        if key == "jssID":
            if not raw.isascii() or not raw.isdigit():
                raise SampleInputError(
                    "Jamf Pro ID must be a whole number, such as 1547."
                )
            value = int(raw)
        else:
            value = raw
        event[key] = value
        applied[key] = value
    return applied


def _jamf_sample_payload(automation: Dict, form: Any) -> Tuple[Dict, Dict]:
    """The payload to send and the device values to remember."""
    pasted = (form.get("payload") or "").strip()
    if pasted:
        try:
            payload = json.loads(pasted)
        except ValueError:
            raise SampleInputError(
                "The sample body is not valid JSON.", title="Invalid JSON"
            )
        if not isinstance(payload, dict):
            raise SampleInputError(
                "The sample body must be a JSON object, in braces.",
                title="Invalid JSON",
            )
    else:
        payload = _jamf_sample(automation)
    return payload, _apply_device_fields(payload, form)


def _remember_sample_device(automation: Dict, applied: Dict) -> None:
    """Save the device the admin used, so the form starts with it."""
    if not applied:
        return
    remembered = dict(automation.get("sample_device") or {})
    remembered.update(applied)
    webhooks = get_all_webhooks()
    data_store.update_webhook_in_list(
        webhooks, automation["name"], {"sample_device": remembered}
    )
    save_all_webhooks(webhooks)


@blueprint.route("/automations/<auto_type>/<name>/test", methods=["POST"])
@login_required
def send_sample(auto_type: str, name: str) -> Union[Response, str]:
    """Run the automation's script once with a sample payload."""
    handler = get_handler(auto_type)
    if not handler:
        abort(404)
    if auto_type not in ("jamfpro", "custom"):
        return _error_page("Not available", SAMPLE_UNSUPPORTED)

    name = str(escape(name))
    automation = get_webhook_by_name(name)
    if not automation:
        return redirect(url_for(LIST_TYPE_ENDPOINT, auto_type=auto_type))

    back = f"/automations/{auto_type}/{name}"
    if auto_type == "jamfpro":
        event = automation.get("event", "")
        if _jamf_sample(automation) is None:
            return render_template(
                "automations/test_result.html",
                handler=handler,
                auto_type=auto_type,
                automation=automation,
                outcome="no_sample",
                event=event,
                back=back,
            )
        try:
            payload, applied = _jamf_sample_payload(automation, request.form)
        except SampleInputError as err:
            return _error_page(
                err.title,
                str(err),
                link=back,
                link_text="Back to the automation",
            )
        _remember_sample_device(automation, applied)
    else:
        pasted = (request.form.get("payload") or "").strip()
        if pasted:
            try:
                payload = json.loads(pasted)
            except ValueError:
                return _error_page(
                    "Invalid JSON",
                    "The sample body is not valid JSON.",
                    link=back,
                    link_text="Back to the automation",
                )
        else:
            payload = {"sample": True}

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} sent a sample "
        f"event to {auto_type} automation {name}"
    )
    output = b""
    try:
        output = jawa_receiver.script_results(payload, automation)
        outcome = "succeeded"
        detail = ""
    except jawa_receiver.ScriptExecutionError as err:
        output = err.output
        outcome = "failed"
        detail = str(err)

    return render_template(
        "automations/test_result.html",
        handler=handler,
        auto_type=auto_type,
        automation=automation,
        outcome=outcome,
        detail=detail,
        output=output.decode("utf-8", errors="replace"),
        payload=json.dumps(payload, indent=2),
        back=back,
    )


@blueprint.route("/automations/tap/<name>/reset-cooldowns", methods=["POST"])
@login_required
def reset_cooldowns(name: str) -> Response:
    """Admin override: let every device run this service again now."""
    automation = get_webhook_by_name(name)
    if not automation or automation.get("tag") != "tap":
        abort(404)
    clear_tap_cooldowns(automation["name"])
    logthis.info(
        f"{session.get('username')} reset the cooldowns for Tap Action "
        f"automation {automation['name']}."
    )
    return redirect(url_for("automations.detail", auto_type="tap", name=name))


PREVIEW_STATES = (
    ("confirm", "Confirm"),
    ("success", "Success"),
    ("failure", "Failure"),
    ("cooldown", "Cooldown"),
)


@blueprint.route("/automations/tap/<name>/preview")
@login_required
def preview_tap(name: str) -> str:
    """Show the device pages with sample values. Nothing here can run
    the script: the preview pages carry no token, no form action and a
    disabled button."""
    from webhook import tap_receiver as receiver

    automation = get_webhook_by_name(name)
    if not automation or automation.get("tag") != "tap":
        abort(404)
    state = request.args.get("state", "confirm")
    if state not in dict(PREVIEW_STATES):
        state = "confirm"
    strings = receiver._page_strings(automation, receiver.SAMPLE_PARAMS)
    context: Dict[str, Any] = {
        "strings": strings,
        "preview": True,
        "service_name": automation["name"],
    }
    if state in ("confirm", "cooldown"):
        template = "tap/confirm.html"
        context["cooldown"] = (
            receiver.cooldown_message(300) if state == "cooldown" else ""
        )
    else:
        template = "tap/result.html"
        context["succeeded"] = state == "success"
    device_page = receiver.render_device_page(template, **context)
    return render_template(
        "automations/tap_preview.html",
        automation=automation,
        states=PREVIEW_STATES,
        state=state,
        device_page=device_page,
    )


# --- Edit ---


@blueprint.route(
    "/automations/<auto_type>/<name>/edit", methods=["GET", "POST"]
)
@login_required
def edit(auto_type: str, name: str) -> Union[Response, str]:
    handler = get_handler(auto_type)
    if not handler or not handler.supports_edit:
        abort(404)

    name = str(escape(name))
    session_data = _get_session_data()

    if auto_type == "cron":
        all_items = get_all_crons()
        existing = next((c for c in all_items if c.get("name") == name), None)
    else:
        all_items = get_all_webhooks()
        existing = next((w for w in all_items if w.get("name") == name), None)

    if not existing:
        logthis.info(f"Automation '{name}' not found for edit")
        return redirect(url_for(LIST_TYPE_ENDPOINT, auto_type=auto_type))

    if request.method == "GET":
        ctx = handler.get_create_context(session_data)
        ctx.update(handler.get_edit_context(existing))
        webhook_info = [existing]
        return render_template(
            "automations/edit.html",
            handler=handler,
            auto_type=auto_type,
            automation_name=name,
            webhook_info=webhook_info,
            cron_info=existing if auto_type == "cron" else None,
            **ctx,
        )

    # POST — check for delete button
    if request.form.get("button_choice") == "Delete":
        return redirect(
            url_for(
                "automations.delete",
                auto_type=auto_type,
                name=name,
            )
        )

    try:
        _check_rename(auto_type, existing, request.form)
        result = handler.process_edit(
            request.form,
            request.files,
            session_data,
            existing,
            all_items,
        )
    except AutomationError as err:
        return _error_page(err.title, err.message, err.link, err.link_text)
    except ValueError as err:
        # e.g. save_script rejecting an upload with no shebang.
        return _error_page("Invalid script", str(err))

    rename_runs(name, existing.get("name", name))

    return _flash_success(
        auto_type=auto_type,
        success_msg=result.get("success_msg", "Updated successfully."),
        new_link=result.get("new_link"),
        new_here=result.get("new_here"),
        smart_group_notice=result.get("smart_group_notice"),
        smart_group_instructions=result.get("smart_group_instructions"),
        extra_notice=result.get("extra_notice"),
        custom_header=result.get("custom_header"),
        webhook_url=result.get("webhook_url"),
        webhook_url_missing=result.get("webhook_url_missing"),
    )


# --- Delete ---


@blueprint.route(
    "/automations/<auto_type>/<name>/delete", methods=["GET", "POST"]
)
@login_required
def delete(auto_type: str, name: str) -> Union[Response, str]:
    handler = get_handler(auto_type)
    if not handler:
        abort(404)

    name = str(escape(name))

    if auto_type == "cron":
        automation = get_cron_by_name(name)
    else:
        automation = get_webhook_by_name(name)

    if not automation:
        return redirect(url_for(LIST_TYPE_ENDPOINT, auto_type=auto_type))

    if request.method == "GET":
        return render_template(
            "automations/delete.html",
            handler=handler,
            auto_type=auto_type,
            automation_name=name,
        )

    # POST — perform deletion
    session_data = _get_session_data()
    error = handler.process_delete(automation, session_data)
    if error:
        return _error_page("Delete Error", error)

    if auto_type == "cron":
        remove_cron(name)
    else:
        remove_webhook(name)
    clear_runs(name)

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} deleted "
        f"{auto_type} automation: {name}"
    )

    success_msg = (
        f"Successfully deleted the {handler.display_name} automation: {name}."
    )
    return _flash_success(auto_type=auto_type, success_msg=success_msg)


# --- Helpers ---


def _check_rename(auto_type: str, existing: Dict, form) -> None:
    """Raise AutomationError when an edit renames to an unusable name.

    Create applies the name rules and the duplicate check; this gives
    edit the same, so a rename cannot produce a name that no URL can
    reach or one that another webhook or cron entry already holds.
    """
    if auto_type not in ("jamfpro", "custom", "cron"):
        return
    new_name = _extract_name(auto_type, form)
    if not new_name or new_name == existing.get("name"):
        return
    validate_webhook_name(new_name)
    if webhook_name_exists(new_name) or cron_name_exists(new_name):
        raise AutomationError("Error", "Name already exists!")


def _extract_name(auto_type: str, form) -> str:
    """Extract the automation name from the form based on type."""
    name_fields = {
        "jamfpro": "webhook_name",
        "okta": "webhookname",
        "custom": "custom_name",
        "cron": "cron_name",
        "tap": "service_name",
    }
    field = name_fields.get(auto_type, "name")
    return form.get(field, "")
