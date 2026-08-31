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

import base64
import json
import os
from typing import Optional, Union

import requests
from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape

from bin import logger
from bin.tokens import get_token, invalidate_token

logthis = logger.setup_child_logger("jawa", __name__)

log_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "jawa.log")
)
server_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "server.json")
)
webhooks_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "webhooks.json")
)
cron_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "cron.json")
)
resources_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)
files_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "resources", "files")
)
img_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "img")
)
verify_ssl = True  # Enables Jamf Pro SSL certificate verification

blueprint = Blueprint("home_view", __name__, template_folder="templates")

LOGOUT_ENDPOINT = "home_view.logout"
DASHBOARD_ENDPOINT = "home_view.dashboard"
HOME_TEMPLATE = "home.html"
ERROR_TITLE_SESSION = "Session Timed Out"
ERROR_MSG_SIGN_IN = "Please sign in again"


def _resolve_url_from_server(form, server_json: dict) -> Optional[str]:
    """Determine the Jamf Pro URL from form data and server config.

    Returns None when the form asks for a host this instance is not
    configured for, which the caller must treat as a failed login.

    `active_url` renders only as a two-option <select> over the URLs the
    operator configured, so the UI presents the server as pinned -- but
    this resolver used to honour whatever a POST supplied. Every gate
    after this point (the token fetch, the activationcode shape check)
    queries *this* URL, so an attacker-chosen host answers all of them
    and none of them authenticates anything. The allow-list is what
    makes those gates meaningful, so it belongs here rather than in
    them.
    """
    configured = [
        _strip_trailing_slash(str(url))
        for url in (
            server_json.get("jps_url"),
            server_json.get("alternate_jps"),
        )
        if url
    ]
    requested = form.get("active_url")
    if requested:
        candidate = _strip_trailing_slash(str(requested))
        if configured and candidate not in configured:
            return None
        return candidate
    if configured:
        return configured[0]
    # No JPS pinned yet (first-time setup): the login form still offers a
    # free-text URL field, and there is nothing to check it against.
    return _strip_trailing_slash(form.get("url", ""))


def _strip_trailing_slash(url: str) -> str:
    """Remove a trailing slash from a URL string."""
    return url.rstrip("/") if url.endswith("/") else url


def _login_error(title: str, message) -> Response:
    """Redirect to logout with an error. Stash the entered username
    and JPS URL (never the password) in the session for one-shot
    re-display on the login page. Using the signed session (not query
    params) prevents an attacker from crafting a link that pre-fills
    the JPS URL field (credential-target phishing)."""
    session["login_retry"] = {
        "username": request.form.get("username", ""),
        "url": request.form.get("url", ""),
    }
    return redirect(
        url_for(LOGOUT_ENDPOINT, error_title=title, error_message=message)
    )


def _validate_credentials() -> Union[Response, None]:
    """Validate password and token, returning a redirect on failure."""
    if request.form["password"] == "":
        return _login_error("Authentication error", "Passwords can't be blank")
    if not session.get("token"):
        return _login_error("Could not fetch token", "try again")
    return None


# Jamf Pro wraps /JSSResource/activationcode in a single top-level key.
# Live instances answer with "license_information"; the resource is also
# published as "activation_code". Accept either: a random website's JSON
# carries neither, which is all this guard has to distinguish. Checking
# for one spelling only locked real operators out of their own console.
_JAMF_ACTIVATION_KEYS = ("license_information", "activation_code")


def _verify_jamf_access() -> Union[Response, None]:
    """Verify Jamf Pro API access, returning a redirect on failure."""
    try:
        resp = requests.get(
            session["url"] + "/JSSResource/activationcode",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {session.get('token')}",
                "User-Agent": "JAWA%20v3.2.0",
            },
            verify=verify_ssl,
        )
        resp.raise_for_status()
        # A reachable non-Jamf site also answers 200 here; confirm the
        # body is the Jamf activationcode JSON shape before trusting it.
        # Any random website returning an HTML 200 must NOT count as a
        # successful Jamf login (defense in depth behind the token check).
        body = resp.json()
        if not isinstance(body, dict) or not any(
            key in body for key in _JAMF_ACTIVATION_KEYS
        ):
            logthis.error(
                f"[{session.get('url')}] activationcode response was not "
                "Jamf-shaped; refusing login."
            )
            return _login_error(
                "Login error",
                "that URL did not respond like a Jamf Pro server",
            )
    except ValueError as err:
        # resp.json() raised: the endpoint returned non-JSON (e.g. an
        # HTML page from a non-Jamf host).
        logthis.error(f"Error occurred: {err}")
        return _login_error(
            "Login error", "that URL did not respond like a Jamf Pro server"
        )
    except requests.exceptions.HTTPError as err:
        logthis.error(f"Error occurred: {err}")
        return _login_error(
            "Login error", "check account credentials and privileges"
        )
    except requests.exceptions.ConnectTimeout as err:
        logthis.error(f"Error occurred: {err}")
        return _login_error("Connection Timeout", err)
    except requests.exceptions.ConnectionError as err:
        logthis.error(f"Error occurred: {err}")
        return _login_error("HTTP Error", err)
    return None


@blueprint.route("/login", methods=["GET", "POST"])
def login() -> Response:
    if request.method == "POST":
        if os.path.isfile(server_file):
            with open(server_file) as json_file:
                server_json = json.load(json_file)
            resolved = _resolve_url_from_server(request.form, server_json)
            if resolved is None:
                logthis.warning(
                    "Refusing a login against an unconfigured Jamf Pro "
                    f"URL: {request.form.get('active_url')!r}"
                )
                return _login_error(
                    "Unrecognized server",
                    "That Jamf Pro server is not one this JAWA is "
                    "configured to use.",
                )
            session["url"] = resolved
        else:
            session["url"] = _strip_trailing_slash(request.form.get("url", ""))

        session["username"] = request.form["username"]
        session["password"] = request.form["password"]
        session["b64_auth"] = base64.b64encode(
            str.encode(f"{session.get('username')}:{session.get('password')}")
        )
        # Honor a token-fetch failure: get_token() returns a redirect
        # when the token endpoint is unreachable or answers with a
        # non-Jamf body. Ignoring it let login proceed on a failed fetch.
        token_error = get_token()
        if token_error:
            return token_error
        logthis.info(
            f"[{session.get('url')}] Attempting login for: "
            f"{session.get('username')}"
        )

        error = _validate_credentials()
        if error:
            return error

        error = _verify_jamf_access()
        if error:
            return error

        logthis.info(
            f"[{session.get('url')}] Logging In: "
            + str(escape(session["username"]))
        )

        session.permanent = True
        return redirect(url_for(DASHBOARD_ENDPOINT))

    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE_SESSION,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    return redirect(url_for(DASHBOARD_ENDPOINT))


@blueprint.route("/logout")
def logout() -> Union[Response, str]:
    error_title = request.args.get("error_title")
    if error_title:
        error_title = escape(error_title)
    error_message = request.args.get("error_message")
    if error_message:
        error_message = escape(error_message)
    if session.get("username"):
        invalidate_token()
        logthis.info("Logging Out: " + str(escape(session["username"])))
        session.pop("username", None)
    # Always clear API token state on logout so a stale token can never
    # outlive the session and satisfy a later login's credential check.
    session.pop("token", None)
    session.pop("expires", None)
    return load_home(error_title, error_message)


def _load_server_config() -> dict:
    """Load server.json, creating it if it doesn't exist."""
    if not os.path.isfile(server_file):
        with open(server_file, "w") as fout:
            json.dump({}, fout)
    with open(server_file, "r") as fin:
        return json.load(fin)


def _render_home(error_title="", error_message="", **kwargs) -> str:
    """Render the home template with common error parameters.

    prev_username/prev_url come from a one-shot session flash set only
    by _login_error (a genuine failed login), never from request args,
    so they cannot be attacker-supplied via a crafted URL. Popped on
    render so they don't persist. Password is never retained.
    """
    retry = session.pop("login_retry", None) or {}
    return render_template(
        HOME_TEMPLATE,
        error_title=error_title,
        error_message=error_message,
        prev_username=retry.get("username", ""),
        prev_url=retry.get("url", ""),
        **kwargs,
    )


def load_home(
    error_title: str = "", error_message: str = ""
) -> Union[Response, str]:
    if "username" in session:
        return redirect(url_for(DASHBOARD_ENDPOINT))

    server_json = _load_server_config()
    if not server_json:
        return _render_home(error_title, error_message)

    brand = server_json.get("brand")
    jps_url = server_json.get("jps_url")

    if not jps_url:
        return _render_home(error_title, error_message, app_name=brand)

    alt_jps = server_json.get("alternate_jps")
    if alt_jps is None:
        return _render_home(error_title, error_message, app_name=brand)

    if alt_jps != "":
        return _render_home(
            error_title,
            error_message,
            jps_url=jps_url,
            jps_url2=alt_jps,
            welcome="true",
            jsslock="true",
            app_name=brand,
        )

    session["url"] = jps_url
    return _render_home(
        error_title,
        error_message,
        jps_url=str(escape(session["url"])),
        welcome="true",
        jsslock="true",
        app_name=brand,
    )


@blueprint.route("/dashboard")
def dashboard() -> Union[Response, str]:
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE_SESSION,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} rendering /dashboard."
    )

    from bin.data_store import get_all_webhooks, get_all_crons
    from views._type_handlers import HANDLERS

    all_webhooks = get_all_webhooks()
    all_crons = get_all_crons()

    categorized = {}
    for tag, handler in HANDLERS.items():
        if tag == "cron":
            items = all_crons
        else:
            items = [w for w in all_webhooks if w.get("tag") == tag]
        categorized[tag] = {"handler": handler, "items": items}

    total_webhooks = len(all_webhooks)
    total_cron = len(all_crons)

    logthis.info(f"Total webhooks managed by JAWA: {total_webhooks}")

    return render_template(
        "dashboard.html",
        categorized=categorized,
        total_webhooks=total_webhooks,
        total_cron=total_cron,
        login="true",
        username=str(escape(session["username"])),
    )


@blueprint.route("/home.html")
def index() -> Union[Response, str]:
    return load_home()
