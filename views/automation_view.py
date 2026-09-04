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

from typing import Any, Union

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

from bin import logger
from bin.auth import login_required
from bin.data_store import (
    add_cron,
    add_webhook,
    get_all_crons,
    get_all_webhooks,
    get_cron_by_name,
    get_webhook_by_name,
    get_webhooks_by_tag,
    remove_cron,
    remove_webhook,
    webhook_name_exists,
    cron_name_exists,
)
from views._type_handlers import HANDLERS, get_handler
from views._type_handlers.base import AutomationError

logthis = logger.setup_child_logger("jawa", "automation_view")

blueprint = Blueprint("automations", __name__)

LIST_TYPE_ENDPOINT = "automations.list_type"


def _get_session_data() -> dict:
    return {
        "url": session.get("url"),
        "username": session.get("username"),
        "password": session.get("password"),
        "token": session.get("token"),
        "expires": session.get("expires"),
        "b64_auth": session.get("b64_auth"),
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

    return render_template(
        "automations/detail.html",
        handler=handler,
        auto_type=auto_type,
        automation=automation,
        detail_fields=detail_fields,
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

    return _flash_success(
        auto_type=auto_type,
        success_msg=result.get("success_msg", "Updated successfully."),
        new_link=result.get("new_link"),
        new_here=result.get("new_here"),
        smart_group_notice=result.get("smart_group_notice"),
        smart_group_instructions=result.get("smart_group_instructions"),
        extra_notice=result.get("extra_notice"),
        custom_header=result.get("custom_header"),
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

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} deleted "
        f"{auto_type} automation: {name}"
    )

    success_msg = (
        f"Successfully deleted the {handler.display_name} automation: {name}."
    )
    return _flash_success(auto_type=auto_type, success_msg=success_msg)


# --- Helpers ---


def _extract_name(auto_type: str, form) -> str:
    """Extract the automation name from the form based on type."""
    name_fields = {
        "jamfpro": "webhook_name",
        "okta": "webhookname",
        "custom": "custom_name",
        "cron": "cron_name",
    }
    field = name_fields.get(auto_type, "name")
    return form.get(field, "")
