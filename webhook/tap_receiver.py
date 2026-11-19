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

"""Device-facing receiver for Tap Action automations.

A Tap Action automation is triggered by a person tapping a web clip on
the managed device itself. The web clip URL carries a per-service
token plus Jamf Pro payload variables (``$JSSID``, ``$UDID`` and any
display values the admin adds). GET renders a confirmation page from
that query string; only the page's POST spawns the script. See the
Tap action section of README.md for the URL and payload contract.
"""

import functools
import hmac
import os
import re
import threading
import time
from urllib.parse import unquote_plus
from typing import Any, Dict, Mapping, Optional, Tuple

from flask import Blueprint, render_template, request
from markupsafe import Markup

from bin import data_store, logger
from webhook.jawa_receiver import ScriptExecutionError, script_results

logthis = logger.setup_child_logger("jawa", "tap_receiver")

blueprint = Blueprint("tap_receiver", __name__, template_folder="templates")

RESERVED_PARAMS = ("token", "id", "udid")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


class TapActionRequestError(Exception):
    """A device request JAWA refuses before anything runs."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def fill_placeholders(text: str, params: Mapping[str, str]) -> str:
    """Substitute ``{NAME}`` with the query-string value of NAME.

    Unknown names render empty. The result is raw text: Jinja escapes
    it at render time, so a caller-supplied value can never become
    markup.
    """
    return _PLACEHOLDER_RE.sub(
        lambda m: str(params.get(m.group(1), "")), text or ""
    )


def parse_device_request(
    fields: Mapping[str, str],
) -> Tuple[int, str, Dict[str, str]]:
    """Split a query string / form into (jss_id, udid, params).

    ``id`` and ``udid`` are required because the script's UDID
    cross-check (ADR-0012) needs both. Everything else that is not
    reserved passes through untouched under ``params``.
    """
    raw_id = (fields.get("id") or "").strip()
    udid = (fields.get("udid") or "").strip()
    if not raw_id or not udid:
        raise TapActionRequestError(
            400, "This link is missing the device id or UDID."
        )
    if not (raw_id.isascii() and raw_id.isdigit()):
        raise TapActionRequestError(400, "The device id is not a number.")
    params = {
        key: value
        for key, value in fields.items()
        if key not in RESERVED_PARAMS
    }
    return int(raw_id), udid, params


def token_matches(service: Dict[str, Any], presented: Optional[str]) -> bool:
    expected = str(service.get("token") or "")
    if not expected or not presented:
        return False
    return hmac.compare_digest(
        expected.encode("utf-8", "surrogateescape"),
        str(presented).encode("utf-8", "surrogateescape"),
    )


def build_tap_payload(
    service: Dict[str, Any],
    jss_id: int,
    udid: str,
    params: Dict[str, str],
    remote_address: str,
) -> Dict[str, Any]:
    """The argv[1] JSON a Tap Action script receives.

    Shaped like a Jamf Pro event so scripts written for
    MobileDeviceEnrolled-style payloads port with a one-line change.
    """
    return {
        "webhook": {
            "webhookEvent": "TapAction",
            "name": service.get("name", ""),
            "eventTimestamp": int(time.time() * 1000),
        },
        "event": {
            "jssID": jss_id,
            "udid": udid,
            "deviceType": service.get("device_family", "mobile"),
            "params": params,
            "remoteAddress": remote_address,
        },
    }


def load_service(name: str) -> Optional[Dict[str, Any]]:
    entry = data_store.get_webhook_by_name(name)
    if not entry or entry.get("tag") != "tap":
        return None
    return entry


def query_fields() -> Dict[str, str]:
    """The GET query string as a dict, split on ';' or '&'.

    The web clip URL Jamf Pro deploys joins parameters with ';'
    because Jamf refuses to store a web clip payload containing '&'.
    Werkzeug splits only on '&', so parse the raw query string here.
    Later duplicates win, matching the usual last-value behaviour.
    """
    raw = request.query_string.decode("utf-8", errors="replace")
    fields: Dict[str, str] = {}
    for pair in re.split(r"[&;]", raw):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        fields[unquote_plus(key)] = unquote_plus(value)
    return fields


def _remote_address() -> str:
    # nginx sets X-Real-IP from the connection address. X-Forwarded-For
    # carries whatever the client sent first, so it is never read.
    real_ip = request.headers.get("X-Real-IP", "").strip()
    return real_ip or request.remote_addr or ""


def _authorize(service_name: str, fields: Mapping[str, str]):
    """Resolve the service and check its token, or raise 401.

    The 401 body never carries the name: it is caller-controlled path
    input and the log line is where an operator looks anyway.
    """
    service = load_service(service_name)
    if not service or not token_matches(service, fields.get("token")):
        logthis.warning(
            f"401 - Tap Action request refused for /tap/"
            f"{service_name} (unknown service or bad token)."
        )
        raise TapActionRequestError(
            401, "Unauthorized - this link is not valid."
        )
    return service


def _page_strings(service: Dict[str, Any], params: Dict[str, str]):
    return {
        key: fill_placeholders(service.get(key, ""), params)
        for key in (
            "page_title",
            "page_description",
            "confirm_label",
            "success_message",
            "failure_message",
        )
    }


SAMPLE_PARAMS = {"DEVICENAME": "Sample iPad", "SERIALNUMBER": "XXXX0000"}

# Copy for the problem page, by error status. The 401 copy never names
# the service: the name is caller-controlled path input.
PROBLEMS = {
    400: {
        "icon": "error",
        "heading": "This button is not set up correctly",
        "body": "Ask your IT team to check this web clip.",
    },
    401: {
        "icon": "error",
        "heading": "This button no longer works",
        "body": "Ask your IT team for a new one.",
    },
    429: {
        "icon": "info",
        "heading": "Please wait a moment",
        "body": "Too many taps in a row. Try again in a minute.",
    },
}


def branding_name() -> str:
    """The organisation name from Setup > Branding, or empty."""
    return str(data_store.get_server_config().get("brand") or "")


ICONS_SVG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "css",
    "vendor",
    "icons.svg",
)
STATUS_ICONS = (
    "circle-check",
    "triangle-exclamation",
    "circle-exclamation",
    "circle-info",
)


@functools.lru_cache(maxsize=1)
def status_icon_symbols() -> Markup:
    """The status icons' <symbol> elements from the vendored icons.svg.

    Device pages carry them inline, so their icons also show inside the
    console's sandboxed preview frame, which cannot load the sprite file.
    """
    with open(ICONS_SVG, encoding="utf-8") as handle:
        sprite = handle.read()
    found = [
        re.search(rf'<symbol id="{name}".*?</symbol>', sprite, re.S)
        for name in STATUS_ICONS
    ]
    return Markup("".join(match.group(0) for match in found if match))


def render_device_page(template: str, **context: Any):
    """Render a device-facing page with the organisation's branding."""
    return render_template(
        template,
        brand_name=branding_name(),
        icon_symbols=status_icon_symbols(),
        **context,
    )


def problem_response(err: "TapActionRequestError"):
    """The HTML page for a refused request, with the same status code."""
    problem = PROBLEMS.get(err.status, PROBLEMS[400])
    # Only the 400 reasons are safe, fixed strings worth showing; the
    # 401 and 429 pages say everything the person needs already.
    detail = err.message if err.status == 400 else ""
    return (
        render_device_page("tap/problem.html", problem=problem, detail=detail),
        err.status,
    )


def _now() -> float:
    return time.time()


def _cooldown_minutes(service: Dict[str, Any]) -> int:
    try:
        return max(0, int(service.get("cooldown_minutes") or 0))
    except (TypeError, ValueError):
        return 0


# Unauthenticated confirms: each service token is shared by every web
# clip, so cap how often one address can make JAWA run the script and
# call Jamf Pro (per service, sliding window, per process).
RATE_LIMIT = 10
RATE_WINDOW = 60.0
_rate_lock = threading.Lock()
_recent: Dict[Tuple[str, str], list] = {}


def reset_rate_limits() -> None:
    with _rate_lock:
        _recent.clear()


def _over_rate_limit(service_name: str, address: str) -> bool:
    now = _now()
    with _rate_lock:
        times = [
            t
            for t in _recent.get((service_name, address), [])
            if now - t < RATE_WINDOW
        ]
        if len(times) >= RATE_LIMIT:
            _recent[(service_name, address)] = times
            return True
        times.append(now)
        _recent[(service_name, address)] = times
        if len(_recent) > 10000:  # bound memory: drop the stalest entries
            for key in sorted(_recent, key=lambda k: max(_recent[k]))[:5000]:
                del _recent[key]
    return False


def cooldown_message(seconds: int) -> str:
    if seconds < 60:
        wait = "under a minute"
    else:
        minutes = -(-seconds // 60)  # round up
        wait = f"about {minutes} minute{'s' if minutes != 1 else ''}"
    return f"This was just done. You can run it again in {wait}."


@blueprint.route("/tap/<service_name>", methods=["GET"])
def service_page(service_name: str):
    logthis.info(f"Incoming GET at /tap/{service_name} ...")
    try:
        fields = query_fields()
        service = _authorize(service_name, fields)
        jss_id, udid, params = parse_device_request(fields)
    except TapActionRequestError as err:
        return problem_response(err)
    wait = data_store.tap_cooldown_remaining(
        service["name"], jss_id, _cooldown_minutes(service), _now()
    )
    return render_device_page(
        "tap/confirm.html",
        cooldown=cooldown_message(wait) if wait else "",
        service_name=service["name"],
        strings=_page_strings(service, params),
        token=fields.get("token", ""),
        jss_id=jss_id,
        udid=udid,
        params=params,
    )


@blueprint.route("/tap/<service_name>", methods=["POST"])
def service_run(service_name: str):
    logthis.info(f"Incoming POST at /tap/{service_name} ...")
    try:
        service = _authorize(service_name, request.form)
        jss_id, udid, params = parse_device_request(request.form)
    except TapActionRequestError as err:
        return problem_response(err)

    if _over_rate_limit(service["name"], _remote_address()):
        logthis.warning(
            f"429 - Tap Action {service['name']}: too many confirms from "
            f"{_remote_address()}."
        )
        return problem_response(
            TapActionRequestError(
                429, "Too many requests. Wait a minute and try again."
            )
        )
    payload = build_tap_payload(
        service, jss_id, udid, params, _remote_address()
    )
    strings = _page_strings(service, params)
    back = {
        "service_name": service["name"],
        "token": request.form.get("token", ""),
        "jss_id": jss_id,
        "udid": udid,
        "params": params,
    }
    wait = data_store.claim_tap_run(
        service["name"], jss_id, _cooldown_minutes(service), _now()
    )
    if wait:
        logthis.info(
            f"Tap action {service['name']} refused for device {jss_id}: "
            f"cooldown, {wait}s left."
        )
        return (
            render_device_page(
                "tap/result.html",
                strings=strings,
                succeeded=False,
                cooldown=cooldown_message(wait),
                **back,
            ),
            429,
        )
    logthis.info(
        f"Tap action {service['name']} confirmed for device {jss_id} "
        f"from {payload['event']['remoteAddress']}; running script..."
    )
    try:
        script_results(payload, service)
    except ScriptExecutionError as err:
        data_store.release_tap_run(service["name"], jss_id)
        logthis.error(
            f"Tap action {service['name']} failed for device {jss_id}: {err}"
        )
        return (
            render_device_page(
                "tap/result.html",
                strings=strings,
                succeeded=False,
                **back,
            ),
            err.status,
        )
    return render_device_page(
        "tap/result.html", strings=strings, succeeded=True, **back
    )
