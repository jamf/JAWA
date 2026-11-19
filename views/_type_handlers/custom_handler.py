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

from typing import Any, Dict, List, Optional, Tuple

from bin import logger
from bin.data_store import (
    get_jawa_address,
    retire_script,
    save_all_webhooks,
    save_script,
)
from views._type_handlers.base import AutomationError, AutomationHandler

logthis = logger.setup_child_logger("jawa", "custom_handler")


def _get_form_value(form: Any, key: str, default: str = "null") -> str:
    value = form.get(key)
    return value if value else default


NO_ADDRESS_HINT = "Set the JAWA server address in Setup to see the full URL"


def hook_url(name: str) -> Optional[str]:
    """The URL a sender must POST to, or None without a server address."""
    address = (get_jawa_address() or "").strip().rstrip("/")
    if not address:
        return None
    return f"{address}/hooks/{name}"


def auth_label(automation: Dict) -> str:
    """Which credentials the endpoint wants. Never includes the values."""
    parts = []
    user = automation.get("webhook_username")
    if user not in (None, "", "null"):
        parts.append(f"Basic (username {user})")
    if automation.get("api_key") not in (None, "", "null"):
        parts.append("x-api-key header")
    return " and ".join(parts) if parts else "None"


class CustomHandler(AutomationHandler):
    tag = "custom"
    display_name = "Custom"
    summary = "Gives you a URL that any system can call to run a script."
    badge_class = "badge-provisioning"
    icon = "webhook.png"
    supports_edit = True
    supports_auth = True
    copyable_labels = ("Script path", "Webhook URL")

    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        return {}

    def process_create(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
    ) -> Dict[str, Any]:
        custom_name = form.get("custom_name", "")
        description = form.get("description", "")
        output = form.get("output")

        if not custom_name:
            raise AutomationError("Error", "Webhook name is required.")
        if " " in custom_name:
            raise AutomationError("Error", "Single-string name only.")

        # Save script
        new_file = files.get("new_file")
        if not new_file or not new_file.filename:
            raise AutomationError("Error", "A script file is required.")
        script_path = save_script(new_file, custom_name)

        # Auth fields
        webhook_user = _get_form_value(form, "basic_username")
        webhook_pass = _get_form_value(form, "new-password")

        if form.get("custom"):
            api_key = _get_form_value(form, "api_key")
            extra_notice = (
                "Use the following in your request headers "
                "for authentication: "
            )
            custom_header = {"x-api-key": f"{api_key}"}
        else:
            api_key = "null"
            extra_notice = None
            custom_header = None

        entry = {
            "url": str(session_data["url"]),
            "jawa_admin": str(session_data["username"]),
            "name": custom_name,
            "webhook_username": webhook_user,
            "webhook_password": webhook_pass,
            "api_key": api_key,
            "script": script_path,
            "description": description,
            "tag": "custom",
            "output": output,
        }

        url = hook_url(custom_name)
        return {
            "entry": entry,
            "success_msg": "Webhook created. Send POST requests to:",
            "webhook_url": url,
            "webhook_url_missing": url is None,
            "new_link": f"/automations/custom/{custom_name}",
            "new_here": "View the webhook details",
            "extra_notice": extra_notice,
            "custom_header": custom_header,
        }

    def process_edit(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
        existing: Dict,
        all_items: Any,
    ) -> Dict[str, Any]:
        name = existing["name"]
        new_name = _get_form_value(form, "custom_name", name)
        description = form.get("description")
        output = form.get("output")

        # Auth fields
        if form.get("basic"):
            webhook_user = _get_form_value(form, "basic_username")
            webhook_pass = _get_form_value(form, "new-password")
        else:
            webhook_user = "null"
            webhook_pass = "null"

        if form.get("custom"):
            api_key = _get_form_value(form, "api_key")
            extra_notice = (
                "Use the following in your request headers "
                "for authentication: "
            )
            custom_header = {"x-api-key": f"{api_key}"}
        else:
            api_key = "null"
            extra_notice = None
            custom_header = None

        existing["webhook_username"] = webhook_user
        existing["webhook_password"] = webhook_pass
        existing["api_key"] = api_key
        existing["name"] = new_name
        existing["output"] = output
        if description:
            existing["description"] = description

        # Handle script upload
        if files.get("new_file") and files["new_file"].filename:
            script_path = save_script(files["new_file"], new_name)
            existing["script"] = script_path

        save_all_webhooks(all_items)

        logthis.info(
            f"{session_data.get('username')} edited a custom webhook ({name})."
        )

        url = hook_url(new_name)
        return {
            "success_msg": f"Edited custom webhook {new_name}.",
            "webhook_url": url,
            "webhook_url_missing": url is None,
            "extra_notice": extra_notice,
            "custom_header": custom_header,
        }

    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        retire_script(automation.get("script", ""))
        return None

    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        fields = [
            ("Automation name", automation.get("name", "")),
            (
                "Webhook URL",
                hook_url(automation.get("name", "")) or NO_ADDRESS_HINT,
            ),
            ("Authentication", auth_label(automation)),
            ("Script path", automation.get("script", "")),
            ("Description", automation.get("description", "")),
        ]
        if automation.get("output"):
            fields.append(("Script output in response", automation["output"]))
        return fields
