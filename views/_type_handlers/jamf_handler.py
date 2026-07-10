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

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from bin import logger
from bin.data_store import (
    get_jawa_address,
    save_script,
    save_all_webhooks,
    retire_script,
)
from bin.tokens import validate_token, get_token
from views._type_handlers.base import AutomationError, AutomationHandler

USER_AGENT_STRING = "JAWA%20v3.1.1"

XML = "application/xml"

logthis = logger.setup_child_logger("jawa", "jamf_handler")
VERIFY_SSL = True

SMART_GROUP_EVENTS = [
    "SmartGroupMobileDeviceMembershipChange",
    "SmartGroupComputerMembershipChange",
    "SmartGroupUserMembershipChange",
]

MOBILE_DISPLAY_FIELDS_XML = (
    "<enable_display_fields_for_group_object>true"
    "</enable_display_fields_for_group_object>"
    "<display_fields>"
    "<display_field><name>Asset Tag</name></display_field>"
    "<display_field><name>Building</name></display_field>"
    "<display_field><name>Department</name></display_field>"
    "<display_field><name>Email Address</name></display_field>"
    "<display_field><name>Last Inventory Update</name></display_field>"
    "<display_field><name>Last Enrollment</name></display_field>"
    "</display_fields>"
)


def _build_auth_xml(form: Any) -> str:
    auth_xml = "<authentication_type>NONE</authentication_type>"
    if form.get("choice") == "basic":
        basic_user = form.get("basic_username", "")
        basic_pass = form.get("basic_password", "")
        if basic_user or basic_pass:
            auth_xml = "<authentication_type>BASIC</authentication_type>"
            if basic_user == "null" and basic_pass == "null":
                auth_xml = "<authentication_type>NONE</authentication_type>"
            else:
                auth_xml += f"<username>{basic_user or 'null'}</username>"
                auth_xml += f"<password>{basic_pass or 'null'}</password>"
    return auth_xml


def _build_webhook_xml(
    name: str,
    enabled: str,
    server_address: str,
    event: str,
    auth_xml: str,
    extra_xml: str,
) -> str:
    return (
        f"<webhook>"
        f"<name>{name}</name>"
        f"<enabled>{enabled}</enabled>"
        f"<url>{server_address}/hooks/{name}</url>"
        f"<content_type>application/json</content_type>"
        f"<event>{event}</event>"
        f"{auth_xml}"
        f"{extra_xml}"
        f"</webhook>"
    )


def _smart_group_info(event: str) -> Tuple[str, str, str, str]:
    """Returns (notice, instructions, enablement, extra_xml)."""
    if event in SMART_GROUP_EVENTS:
        notice = "NOTICE!  This webhook is not yet enabled."
        instructions = "Specify desired Smart Group and enable: "
        enablement = "false"
    else:
        notice = ""
        instructions = ""
        enablement = "true"

    if event == "SmartGroupMobileDeviceMembershipChange":
        extra_xml = MOBILE_DISPLAY_FIELDS_XML
    else:
        extra_xml = ""

    return notice, instructions, enablement, extra_xml


def _extract_auth_fields(form: Any) -> Tuple[str, str, str, Any, Any]:
    """Extract auth fields from form. Returns (user, pass, apikey, extra_notice, custom_header)."""
    if form.get("choice") == "basic":
        webhook_user = form.get("basic_username", "null")
        webhook_pass = form.get("basic_password", "null")
    else:
        webhook_user = "null"
        webhook_pass = "null"

    if form.get("choice") == "custom":
        webhook_apikey = form.get("api_key", "null")
        extra_notice = (
            "Copy and paste the following into the Header "
            "Authentication section of Jamf Pro webhooks:"
        )
        custom_header = {"x-api-key": f"{webhook_apikey}"}
    else:
        webhook_apikey = "null"
        extra_notice = None
        custom_header = None

    return (
        webhook_user,
        webhook_pass,
        webhook_apikey,
        extra_notice,
        custom_header,
    )


class JamfHandler(AutomationHandler):
    tag = "jamfpro"
    display_name = "Jamf Pro"
    badge_class = "badge-extensions"
    icon = "webhook.png"
    supports_edit = True
    supports_auth = True

    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        return {"url": session_data.get("url")}

    def process_create(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
    ) -> Dict[str, Any]:
        webhook_name = form.get("webhook_name", "")
        event = form.get("event", "")
        description = form.get("description", "")

        if not webhook_name:
            raise AutomationError("Error", "Webhook name is required.")
        if " " in webhook_name:
            raise AutomationError("Error", "Single-string name only.")

        server_address = get_jawa_address()
        if not server_address:
            raise AutomationError(
                "Setup Required",
                "Configure your JAWA address and Jamf Pro server "
                "before creating an automation.",
                link="/setup",
                link_text="Go to Setup",
            )

        # Ensure token is valid
        if not validate_token(session_data.get("expires")):
            get_token()

        # Save script
        new_file = files.get("new_file")
        if not new_file or not new_file.filename:
            raise AutomationError("Error", "A script file is required.")
        script_path = save_script(new_file, webhook_name)

        # Smart group handling
        notice, instructions, enablement, extra_xml = _smart_group_info(event)

        # Auth
        auth_xml = _build_auth_xml(form)
        (
            webhook_user,
            webhook_pass,
            webhook_apikey,
            extra_notice,
            custom_header,
        ) = _extract_auth_fields(form)

        # Build XML and POST to Jamf
        xml_data = _build_webhook_xml(
            webhook_name,
            enablement,
            server_address,
            event,
            auth_xml,
            extra_xml,
        )
        full_url = session_data["url"] + "/JSSResource/webhooks/id/0"
        logthis.info(
            f"{session_data.get('username')} creating a new JPS webhook "
            f"{webhook_name}."
        )

        try:
            resp = requests.post(
                full_url,
                headers={
                    "Content-Type": XML,
                    "Authorization": f"Bearer {session_data['token']}",
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
                f"Request to Jamf Pro server timed out after 30 seconds. {err}",
            )
        except requests.exceptions.ConnectionError as err:
            logthis.error(
                f"Connection error creating Jamf webhook {webhook_name}: {err}"
            )
            raise AutomationError(
                "Connection Error",
                f"Could not connect to Jamf Pro server. Check network connectivity. {err}",
            )
        except Exception as err:
            logthis.error(
                f"Unexpected error creating Jamf webhook {webhook_name}: {err}"
            )
            raise AutomationError(
                "API Error", f"Failed to create webhook in Jamf Pro. {err}"
            )

        logthis.info(f"[{resp.status_code}]  {resp.text}")

        if resp.status_code == 409:
            logthis.error(
                f"Duplicate webhook name {webhook_name} in Jamf Pro (status 409)"
            )
            raise AutomationError(
                "Duplicate",
                f'The webhook name "{webhook_name}" already exists in '
                f"your Jamf Pro Server.",
            )
        elif resp.status_code >= 400:
            logthis.error(
                f"Jamf API error creating webhook {webhook_name}: "
                f"HTTP {resp.status_code} - {resp.text}"
            )
            raise AutomationError(
                "API Error",
                f"Jamf Pro returned HTTP {resp.status_code}. "
                f"Check permissions and server configuration.",
            )

        result = re.search("<id>(.*)</id>", resp.text)
        jamf_id = result.group(1) if result else ""
        new_link = f"{session_data['url']}/webhooks.html?id={jamf_id}&o=r"

        entry = {
            "url": str(session_data["url"]),
            "jawa_admin": str(session_data["username"]),
            "name": webhook_name,
            "webhook_username": webhook_user,
            "webhook_password": webhook_pass,
            "api_key": webhook_apikey,
            "event": event,
            "script": script_path,
            "description": description,
            "tag": "jamfpro",
            "jamf_id": jamf_id,
        }

        return {
            "entry": entry,
            "success_msg": "New webhook created:",
            "new_link": new_link,
            "new_here": webhook_name,
            "smart_group_notice": notice,
            "smart_group_instructions": instructions,
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
        if not validate_token(session_data.get("expires")):
            get_token()

        name = existing["name"]
        new_name = form.get("webhook_name") or name
        description = form.get("description", existing.get("description"))
        new_event = form.get("event") or existing.get("event")

        (
            webhook_user,
            webhook_pass,
            webhook_apikey,
            extra_notice,
            custom_header,
        ) = _extract_auth_fields(form)

        # Handle script upload
        if files.get("new_file") and files["new_file"].filename:
            script_path = save_script(files["new_file"], new_name)
        else:
            script_path = existing.get("script", "")

        # Update the entry in the list
        existing["name"] = new_name
        existing["description"] = description
        existing["event"] = new_event
        existing["webhook_username"] = webhook_user
        existing["webhook_password"] = webhook_pass
        existing["api_key"] = webhook_apikey
        existing["script"] = script_path
        existing["jawa_admin"] = session_data.get("username")

        # Smart group handling
        notice, instructions, enablement, extra_xml = _smart_group_info(
            new_event
        )

        # Auth XML
        auth_xml = _build_auth_xml(form)

        # Build XML and PUT to Jamf
        server_address = get_jawa_address()
        xml_data = _build_webhook_xml(
            new_name,
            enablement,
            server_address,
            new_event,
            auth_xml,
            extra_xml,
        )
        full_url = (
            f"{session_data['url']}/JSSResource/webhooks/id/"
            f"{existing.get('jamf_id')}"
        )

        try:
            resp = requests.put(
                full_url,
                headers={
                    "Content-Type": XML,
                    "Authorization": f"Bearer {session_data['token']}",
                    "User-Agent": USER_AGENT_STRING,
                },
                data=xml_data,
                verify=VERIFY_SSL,
                timeout=30,
            )
        except requests.exceptions.Timeout as err:
            logthis.error(f"Timeout editing Jamf webhook {new_name}: {err}")
            raise AutomationError(
                "Connection Timeout",
                f"Request to Jamf Pro server timed out after 30 seconds. {err}",
            )
        except requests.exceptions.ConnectionError as err:
            logthis.error(f"Connection error editing Jamf webhook {new_name}: {err}")
            raise AutomationError(
                "Connection Error",
                f"The request could not be sent to your Jamf Pro server, "
                f"check your network connection. Details: {err}",
            )
        except Exception as err:
            logthis.error(f"Unexpected error editing Jamf webhook {new_name}: {err}")
            raise AutomationError(
                "Connection Error",
                f"The request could not be sent to your Jamf Pro server, "
                f"check your network connection. Details: {err}",
            )

        if resp.status_code == 409:
            logthis.error(
                f"Duplicate webhook name {new_name} in Jamf Pro (status 409)"
            )
            raise AutomationError(
                "Duplicate",
                f'The webhook name "{new_name}" already exists in '
                f"your Jamf Pro Server.",
            )
        elif resp.status_code == 401:
            logthis.error(
                f"Insufficient privileges for {session_data.get('username')} "
                f"to edit webhook {new_name} (status 401)"
            )
            raise AutomationError(
                "Insufficient privileges",
                f"{session_data.get('username')} doesn't have privileges "
                f"to update webhooks. Check your account privileges in "
                f"Jamf Pro Settings.",
            )
        elif resp.status_code >= 400:
            logthis.error(
                f"Jamf API error editing webhook {new_name}: "
                f"HTTP {resp.status_code} - {resp.text}"
            )
            raise AutomationError(
                "API Error",
                f"Jamf Pro returned HTTP {resp.status_code}. "
                f"Check permissions and server configuration.",
            )

        # Save updated list
        save_all_webhooks(all_items)

        result = re.search("<id>(.*)</id>", resp.text)
        jamf_id = result.group(1) if result else existing.get("jamf_id")
        new_link = f"{session_data['url']}/webhooks.html?id={jamf_id}&o=r"

        logthis.info(
            f"{session_data.get('username')} edited a Jamf webhook. "
            f"Name: {name} Jamf link: {new_link}"
        )

        return {
            "success_msg": "Webhook edited:",
            "new_link": new_link,
            "new_here": new_name,
            "smart_group_notice": notice,
            "smart_group_instructions": instructions,
            "extra_notice": extra_notice,
            "custom_header": custom_header,
        }

    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        if not validate_token(session_data.get("expires")):
            get_token()
        # Disable and rename in Jamf Pro
        data = (
            f"<webhook><name>{automation['name']}.old.{time.time()}</name>"
            f"<enabled>false</enabled></webhook>"
        )
        full_url = (
            f"{session_data['url']}/JSSResource/webhooks/name/"
            f"{automation['name']}"
        )
        try:
            resp = requests.put(
                full_url,
                headers={
                    "Content-Type": XML,
                    "Authorization": f"Bearer {session_data['token']}",
                    "User-Agent": USER_AGENT_STRING,
                },
                data=data,
                timeout=30,
            )
            if resp.status_code >= 400:
                logthis.error(
                    f"Error disabling Jamf webhook {automation['name']}: "
                    f"HTTP {resp.status_code}"
                )
        except Exception as err:
            logthis.error(
                f"Failed to disable Jamf webhook {automation['name']}: {err}"
            )
        retire_script(automation.get("script", ""))
        return None

    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        fields = [
            ("Automation name", automation.get("name", "")),
            ("Event", automation.get("event", "")),
            ("Script path", automation.get("script", "")),
            ("Description", automation.get("description", "")),
            ("Jamf Pro Server", automation.get("url", "")),
            ("Created by", automation.get("jawa_admin", "")),
        ]
        if automation.get("jamf_id"):
            fields.append(("Jamf ID", automation["jamf_id"]))
        return fields
