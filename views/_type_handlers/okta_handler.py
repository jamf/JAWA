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
from typing import Any, Dict, List, Optional, Tuple

import requests

from bin import logger
from bin.data_store import get_jawa_address, save_script, retire_script
from views._type_handlers.base import AutomationError, AutomationHandler

logthis = logger.setup_child_logger("jawa", "okta_handler")

_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OKTA_VERIFICATION_FILE = os.path.abspath(
    os.path.join(_base_dir, "bin", "okta_verification.py")
)


class OktaHandler(AutomationHandler):
    tag = "okta"
    display_name = "Okta"
    badge_class = "badge-observability"
    icon = "webhook.png"
    supports_edit = False
    supports_auth = False

    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        return {}

    def process_create(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
    ) -> Dict[str, Any]:
        okta_name = form.get("webhookname", "")
        okta_server = form.get("okta_server", "")
        okta_token = form.get("token", "")
        okta_event = form.get("event", "")
        description = form.get("description", "")

        if not okta_name:
            raise AutomationError("Error", "Webhook name is required.")
        if " " in okta_name:
            raise AutomationError("Error", "Single-string name only.")

        server_address = get_jawa_address()
        if not server_address:
            raise AutomationError(
                "Setup Required", "Please configure JAWA address first."
            )

        # Ensure okta verification file is executable
        if os.path.isfile(OKTA_VERIFICATION_FILE):
            os.chmod(OKTA_VERIFICATION_FILE, mode=0o0755)

        # Save script
        script_file_obj = files.get("script")
        if not script_file_obj or not script_file_obj.filename:
            raise AutomationError("Error", "A script file is required.")
        script_path = save_script(script_file_obj, okta_name, "_")

        # Build Okta event hook payload
        webhook_url = f"{server_address}/hooks/{okta_name}"
        logthis.info(webhook_url)

        payload = {
            "name": okta_name,
            "events": {"type": "EVENT_TYPE", "items": [okta_event]},
            "channel": {
                "type": "HTTP",
                "version": "1.0.0",
                "config": {
                    "uri": webhook_url,
                    "headers": [
                        {
                            "key": "X-Other-Header",
                            "value": "some-other-value",
                        }
                    ],
                    "authScheme": {
                        "type": "HEADER",
                        "key": "Authorization",
                        "value": "${api_key}",
                    },
                },
            },
        }

        # Create hook in Okta
        try:
            resp = requests.post(
                f"{okta_server}/api/v1/eventHooks",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"SSWS {okta_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(payload, indent=4),
                timeout=30,
            )
        except requests.exceptions.Timeout as err:
            logthis.error(f"Timeout creating Okta webhook {okta_name}: {err}")
            raise AutomationError(
                "Connection Timeout",
                f"Request to Okta server timed out after 30 seconds. {err}",
            )
        except requests.exceptions.ConnectionError as err:
            logthis.error(f"Connection error creating Okta webhook {okta_name}: {err}")
            raise AutomationError(
                "Connection Error",
                f"Could not connect to Okta server. Check network connectivity. {err}",
            )
        except Exception as err:
            logthis.error(f"Unexpected error creating Okta webhook {okta_name}: {err}")
            raise AutomationError(
                "API Error", f"Failed to create webhook in Okta. {err}"
            )

        try:
            response_json = resp.json()
        except json.JSONDecodeError as err:
            logthis.error(
                f"Invalid JSON response from Okta for webhook {okta_name}: {err}"
            )
            raise AutomationError(
                "API Error",
                f"Okta returned invalid JSON response. Status: {resp.status_code}",
            )

        okta_id = response_json.get("id")

        if not okta_id:
            logthis.error(
                f"Failed to create Okta webhook {okta_name}. "
                f"Response: {response_json}"
            )
            raise AutomationError(
                "Okta Error",
                "Failed to create the event hook in Okta. "
                "Check your Okta server URL and token.",
            )

        entry = {
            "name": okta_name,
            "okta_id": okta_id,
            "okta_event": okta_event,
            "okta_url": okta_server,
            "okta_token": okta_token,
            "script": script_path,
            "description": description,
            "webhook_username": "null",
            "webhook_password": "null",
            "tag": "okta",
        }

        # Verify/activate the hook
        try:
            verify_resp = requests.post(
                f"{okta_server}/api/v1/eventHooks/{okta_id}/lifecycle/verify",
                headers={"Authorization": f"SSWS {okta_token}"},
                timeout=30,
            )
            verification = verify_resp.json()
        except requests.exceptions.Timeout as err:
            logthis.error(f"Timeout verifying Okta webhook {okta_name}: {err}")
            raise AutomationError(
                "Connection Timeout",
                f"Verification request timed out after 30 seconds. {err}",
            )
        except requests.exceptions.ConnectionError as err:
            logthis.error(f"Connection error verifying Okta webhook {okta_name}: {err}")
            raise AutomationError(
                "Connection Error",
                f"Could not connect to Okta for verification. {err}",
            )
        except json.JSONDecodeError as err:
            logthis.error(f"Invalid verification response for webhook {okta_name}: {err}")
            raise AutomationError(
                "API Error", f"Okta returned invalid verification response. {err}"
            )
        except Exception as err:
            logthis.error(f"Unexpected error verifying Okta webhook {okta_name}: {err}")
            raise AutomationError("API Error", f"Failed to verify webhook. {err}")

        if "errorCode" in verification:
            logthis.warning(
                f"Okta webhook verification failed for {okta_name}: {verification}"
            )
            raise AutomationError(
                "Event Verification Error",
                "Okta was unable to verify the webhook. "
                "Check network settings.",
            )

        return {
            "entry": entry,
            "success_msg": "Okta Webhook Created.",
        }

    def process_edit(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
        existing: Dict,
        all_items: Any,
    ) -> Dict[str, Any]:
        raise AutomationError(
            "Not Supported",
            "Okta webhooks cannot be edited. Delete and recreate instead.",
        )

    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        try:
            okta_url = automation.get("okta_url", "")
            okta_id = automation.get("okta_id", "")
            okta_token = automation.get("okta_token", "")
            # Deactivate then delete
            deactivate_resp = requests.post(
                f"{okta_url}/api/v1/eventHooks/{okta_id}/lifecycle/deactivate",
                headers={"Authorization": f"SSWS {okta_token}"},
                timeout=30,
            )
            if deactivate_resp.status_code >= 400:
                logthis.error(
                    f"Error deactivating Okta webhook {automation.get('name')}: "
                    f"HTTP {deactivate_resp.status_code}"
                )

            delete_resp = requests.delete(
                f"{okta_url}/api/v1/eventHooks/{okta_id}",
                headers={"Authorization": f"SSWS {okta_token}"},
                timeout=30,
            )
            if delete_resp.status_code >= 400:
                logthis.error(
                    f"Error deleting Okta webhook {automation.get('name')}: "
                    f"HTTP {delete_resp.status_code}"
                )
        except requests.exceptions.MissingSchema as err:
            logthis.error(
                f"Invalid Okta URL for webhook {automation.get('name')}: {err}"
            )
            return str(err)
        except Exception as err:
            logthis.error(
                f"Failed to delete Okta webhook {automation.get('name')}: {err}"
            )
        retire_script(automation.get("script", ""))
        return None

    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        return [
            ("Automation name", automation.get("name", "")),
            ("Event", automation.get("okta_event", "")),
            ("Script path", automation.get("script", "")),
            ("Okta URL", automation.get("okta_url", "")),
            ("Description", automation.get("description", "")),
        ]
