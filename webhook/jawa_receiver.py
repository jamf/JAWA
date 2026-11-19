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
import hmac
import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from bin import data_store
from bin import failure_alert
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


class ScriptExecutionError(Exception):
    """The automation's script could not be run, or exited non-zero.

    Raised instead of returning the error text, because a returned value
    is indistinguishable from script stdout and the caller then answers
    2xx either way -- the same "reports success, did nothing" shape that
    made template webhooks appear to fire for a whole release.

    ``output`` holds whatever the script printed before it failed.
    ``exit_code`` is the script's exit status when it ran and exited
    non-zero; it stays None when the script never started or timed out.
    """

    output: bytes = b""
    status: int = 500
    exit_code: Optional[int] = None


class ScriptTimeoutError(ScriptExecutionError):
    """The script ran past JAWA_SCRIPT_TIMEOUT and its process group was killed."""

    status = 504


DEFAULT_SCRIPT_TIMEOUT = 120.0


def script_timeout() -> float:
    """Seconds a script may run, from JAWA_SCRIPT_TIMEOUT (default 120)."""
    raw = os.environ.get("JAWA_SCRIPT_TIMEOUT")
    try:
        value = float(raw) if raw else DEFAULT_SCRIPT_TIMEOUT
    except ValueError:
        return DEFAULT_SCRIPT_TIMEOUT
    return value if value > 0 else DEFAULT_SCRIPT_TIMEOUT


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
            # A Tap Action automation is only reachable through
            # /tap/<name> with its token. Its record carries the
            # "null" auth sentinels, which would otherwise make
            # /hooks/<name> an open, token-free way to run the script.
            if each_webhook.get("tag") == "tap":
                logthis.warning(
                    f"Rejecting /hooks/{webhook_name}: Tap Action "
                    "automations only run from /tap/."
                )
                return False
            truth_test = True
            if each_webhook.get("tag") == "okta":
                # Okta sends the stored secret verbatim as the
                # Authorization header. An entry created before secrets
                # existed has none, so it fails closed.
                secret = each_webhook.get("okta_secret")
                if not secret:
                    logthis.warning(
                        f"Rejecting /hooks/{webhook_name}: this Okta "
                        "automation has no secret. Delete and re-create it."
                    )
                    return False
                supplied = request.headers.get("Authorization", "")
                return hmac.compare_digest(
                    supplied.encode("utf-8"), str(secret).encode("utf-8")
                )
            if (
                # Missing auth keys default to the "null" no-auth
                # sentinel so a legacy/hand-edited entry degrades to
                # the documented open-webhook behavior, never a silent
                # 401. Canonical shape is written by data_store; see
                # template_view + custom_handler.
                each_webhook.get("webhook_username", "null") != webhook_user
                or each_webhook.get("webhook_password", "null") != webhook_pass
                or each_webhook.get("api_key", "null") != webhook_apikey
            ):
                truth_test = False
            # Stop at the first name match. Without this, two entries
            # sharing a name let the LAST decide authentication while
            # run_script executes the FIRST.
            break

    return truth_test


def run_script(webhook_data: JSONType, webhook_name: str) -> Optional[bytes]:
    webhooks_json = load_json(jp_webhooks_file)
    for each_webhook in webhooks_json:
        if each_webhook["name"] == webhook_name:
            return script_results(webhook_data, each_webhook)


def _record_run(
    name: Optional[str],
    started: str,
    began: float,
    exit_code: Optional[int],
    output: bytes,
) -> None:
    """Remember this run for the automation's detail page. Never raises."""
    if not name:
        return
    try:
        head_lines = output.decode("utf-8", errors="replace").splitlines()
        head = "\n".join(head_lines[:5])[:500]
        data_store.record_run(
            name, started, time.monotonic() - began, exit_code, head
        )
    except Exception as err:
        logthis.warning(f"Could not record run of {name}: {err}")


def script_results(webhook_data: JSONType, each_webhook: Dict) -> bytes:
    webhook_data = json.dumps(webhook_data)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    began = time.monotonic()
    return_code: Optional[int] = None
    output = b""
    try:
        proc = subprocess.Popen(
            [each_webhook["script"], f"{webhook_data}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        timed_out = threading.Event()

        def _kill_group() -> None:
            timed_out.set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        timer = threading.Timer(script_timeout(), _kill_group)
        timer.daemon = True
        timer.start()
        try:
            output = proc.stdout.read()
            return_code = proc.wait()
        finally:
            timer.cancel()
        if timed_out.is_set():
            logthis.error(
                f"Script for {each_webhook.get('name')} timed out after "
                f"{script_timeout():g}s; its process group was killed."
            )
            failure = ScriptTimeoutError(
                f"script timed out after {script_timeout():g} seconds"
            )
            failure.output = output
            raise failure

        # Tolerant for the same reason as the response decode below: a
        # script that exited 0 must not be turned into a failure by the
        # bytes it chose to print. Strict decode here raised before the
        # response path was ever reached.
        for each_line in output.decode("utf-8", errors="replace").split("\n"):
            if each_line:
                logthis.info(f"{each_webhook.get('name')} - {each_line}")

        if return_code != 0:
            logthis.error(
                f"Script execution failed for {each_webhook.get('name')} "
                f"with exit code {return_code}"
            )
            failure = ScriptExecutionError(f"script exited {return_code}")
            failure.output = output
            failure.exit_code = return_code
            raise failure

        return output
    except ScriptExecutionError:
        raise
    except Exception as err:
        logthis.error(
            f"Error executing script for webhook {each_webhook.get('name')}: {err}"
        )
        if not output:
            output = str(err).encode("utf-8", errors="replace")
        failure = ScriptExecutionError(str(err))
        failure.output = output
        raise failure from err
    finally:
        _record_run(
            each_webhook.get("name"), started, began, return_code, output
        )


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


# Failure alerts: at most one per automation in this window. Kept in memory,
# so it resets on restart, which is acceptable for a chat nudge. The
# sending core lives in bin/failure_alert.py, shared with timed runs.
ALERT_INTERVAL_SECONDS = failure_alert.ALERT_INTERVAL_SECONDS
_alert_lock = threading.Lock()
_last_alert_at: Dict[str, float] = {}


def _failure_alert_url() -> str:
    """The chat webhook set on /setup, or "" when none is configured."""
    return failure_alert.alert_url(server_json_file)


def _post_failure_alert(url: str, text: str) -> None:
    # Runs in a daemon thread. Never raises.
    failure_alert.post(url, text, log=logthis)


def _start_alert_thread(target: Any, args: Tuple[Any, ...]) -> None:
    threading.Thread(
        target=target, args=args, daemon=True, name="jawa-failure-alert"
    ).start()


def notify_run_failed(webhook_name: str, err: ScriptExecutionError) -> None:
    """Tell the configured chat webhook that a run failed. Never raises."""
    try:
        url = _failure_alert_url()
        if not url:
            return
        now = time.monotonic()
        with _alert_lock:
            last = _last_alert_at.get(webhook_name)
            if last is not None and now - last < ALERT_INTERVAL_SECONDS:
                return
            _last_alert_at[webhook_name] = now
        code = err.exit_code if err.exit_code is not None else "n/a"
        text = failure_alert.alert_text(webhook_name, code)
        _start_alert_thread(_post_failure_alert, (url, text))
    except Exception as alert_err:
        logthis.warning(
            f"Failure alert for {webhook_name} was not queued: {alert_err}"
        )


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
    if request.method != "POST":
        logthis.warning(
            f"Invalid request, {request.method} for /hooks/{webhook_name}."
        )
        return (
            "405 - Method not allowed. These aren't the droids you're looking for. You can go about your business. "
            "Move along.",
            405,
        )
    try:
        webhook_data = request.get_json()
    except Exception as err:
        logthis.warning(
            f"Error loading JSON ({err}). Trying to load from form payload."
        )
        raw = request.form.get("payload")
        try:
            webhook_data = json.loads(raw) if raw else None
        except (ValueError, TypeError):
            webhook_data = None
    if not webhook_data:
        logthis.warning(
            f"418.  Error processing /hooks/{webhook_name} - no data provided. I'm a teapot."
        )
        return "418 - I'm a teapot.", 418
    logthis.debug(f"{webhook_name} payload: {webhook_data}")
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
        try:
            raw = run_script(webhook_data, webhook_name)
        except ScriptExecutionError as err:
            # Never answer 2xx for a script that did not run: Jamf Pro
            # records delivery status, and a 200 here is what made a dead
            # automation indistinguishable from a working one.
            notify_run_failed(webhook_name, err)
            return {
                "webhook": f"{webhook_name}",
                "error": str(err),
            }, err.status
        if raw is None:
            logthis.error(
                f"Webhook {webhook_name} disappeared between validation "
                "and execution; nothing ran."
            )
            return {"webhook": f"{webhook_name}", "error": "not found"}, 404
        # Match the decode used for the log lines above. A device name
        # with an accent is not an error, and decode("ascii") turned a
        # SUCCESSFUL run into a 500 that Jamf Pro then retried.
        output = raw.decode("utf-8", errors="replace")
        if custom_output and webhook_tag == "custom":
            return {"webhook": f"{webhook_name}", "result": f"{output}"}, 202
        else:
            return {
                "webhook": f"{webhook_name}",
                "result": "valid webhook received",
            }
    else:
        logthis.warning(
            f"401 - Incorrect authentication provided for /hooks/{webhook_name}."
        )
        # webhook_name is caller-controlled path input, and a bare-string
        # return is served as text/html -- interpolating it here reflected
        # unescaped markup back onto JAWA's own origin. The name is already
        # on the log line above, which is where an operator debugging a 401
        # actually looks.
        return (
            "Unauthorized - incorrect authentication provided.",
            401,
        )
