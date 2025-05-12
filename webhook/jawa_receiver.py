# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2022 Jamf.  All rights reserved.
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

from flask import Blueprint, request
import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

from bin import okta_verification
from bin import logger

JSONType = Union[Dict[str, Any], List[Any], str, int, float, bool, None]

logthis = logger.setup_child_logger("jawa", "webhook_receiver")

server_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "server.json")
)
jp_webhooks_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "webhooks.json")
)
scripts_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)

blueprint = Blueprint("jawa_receiver", __name__, template_folder="templates")


def load_json(file_path: str) -> Union[Dict[str, Any], List[Any]]:
    with open(file_path, "r") as fin:
        return json.load(fin)


def validate_webhook(
    webhook_name: str,
    webhook_user: str,
    webhook_pass: str,
    webhook_apikey: str,
) -> bool:
    webhooks_json = load_json(jp_webhooks_file)
    truth_test = False
    for each_webhook in webhooks_json:
        if each_webhook["name"] == webhook_name:
            truth_test = True
            if (
                each_webhook.get("webhook_username") != webhook_user
                or each_webhook.get("webhook_password") != webhook_pass
                or each_webhook.get("api_key", "null") != webhook_apikey
            ):
                truth_test = False

    return truth_test


def run_script(webhook_data: JSONType, webhook_name: str) -> Optional[bytes]:
    webhooks_json = load_json(jp_webhooks_file)
    for each_webhook in webhooks_json:
        if each_webhook["name"] == webhook_name:
            return script_results(webhook_data, each_webhook)


def script_results(webhook_data: JSONType, each_webhook: Dict) -> bytes:
    webhook_data = json.dumps(webhook_data)
    proc = subprocess.Popen(
        [each_webhook["script"], f"{webhook_data}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.read()
    for each_line in output.decode().split("\n"):
        if each_line:
            logthis.info(f"{each_webhook.get('name')} - {each_line}")
    return output


def custom_output_options(
    webhook_name: str,
) -> Union[Tuple[Any, Any], Tuple[None, None]]:
    webhooks_json = load_json(jp_webhooks_file)
    for each_webhook in webhooks_json:
        if each_webhook["name"] == webhook_name:
            webhook_tag = each_webhook.get("tag")
            send_output = each_webhook.get("output")
            return webhook_tag, send_output
    return None, None


@blueprint.route("/hooks/<webhook_name>", methods=["POST", "GET"])
def webhook_handler(
    webhook_name: str,
) -> Union[Dict[str, Any], Tuple[str, int]]:
    logthis.info(f"Incoming request at /hooks/{webhook_name} ...")
    if request.headers.get("x-okta-verification-challenge"):
        logthis.info("This is an Okta verification challenge...")
        return okta_verification.verify_new_webhook(
            request.headers.get("x-okta-verification-challenge")
        )
    try:
        webhook_data = request.get_json()
    except Exception as err:
        logthis.debug(
            f"Error loading JSON ({err}). Trying to load from form payload."
        )
        webhook_data = json.loads(request.form.get("payload"))
    if not webhook_data:
        logthis.info(
            f"418.  Error processing /hooks/{webhook_name} - no data provided. I'm a teapot."
        )
        return "418 - I'm a teapot.", 418
    logthis.debug(f"{webhook_name} payload: {webhook_data}")
    if request.method != "POST":
        logthis.info(
            f"Invalid request, {request.method} for /hooks/{webhook_name}."
        )
        return (
            "405 - Method not allowed. These aren't the droids you're looking for. You can go about your business. "
            "Move along.",
            405,
        )
    webhook_user = "null"
    webhook_pass = "null"
    webhook_apikey = "null"
    auth = request.authorization
    headers = request.headers
    apikey = headers.get("x-api-key")
    if auth:
        webhook_user = auth.get("username")
        webhook_pass = auth.get("password")
    if apikey:
        webhook_apikey = request.headers.get("x-api-key")
    if validate_webhook(
        webhook_name, webhook_user, webhook_pass, webhook_apikey
    ):
        logthis.info(
            f"Validated authentication for /hooks/{webhook_name}, running script..."
        )
        webhook_tag, custom_output = custom_output_options(webhook_name)
        output = run_script(webhook_data, webhook_name).decode("ascii")
        if custom_output and webhook_tag == "custom":
            return {"webhook": f"{webhook_name}", "result": f"{output}"}, 202
        else:
            return {
                "webhook": f"{webhook_name}",
                "result": "valid webhook received",
            }
    else:
        logthis.info(
            f"401 - Incorrect authentication provided for /hooks/{webhook_name}."
        )
        return (
            f"Unauthorized - incorrect authentication provided for /hooks/{webhook_name}.",
            401,
        )
