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

import base64
from datetime import datetime, timezone, timedelta
from flask import Response, session, redirect, url_for
import requests
from typing import Any, Dict, Optional

from bin import logger

logthis = logger.setup_child_logger("jawa", __name__)


SESSION_ENDED_TITLE = "Session ended"
SESSION_ENDED_MESSAGE = "Your Jamf Pro session ended. Sign in again."

# Renew a token once less than this is left. Every signed-in console
# request checks it (app.py), so an admin who keeps working keeps a live
# token; Jamf Pro tokens last 30 minutes by default.
RENEW_MARGIN = timedelta(minutes=15)

_EXPIRES_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class SessionEnded(Exception):
    """The admin's Jamf Pro token can no longer be renewed.

    The session has already been cleared when this is raised; the app
    turns it into a redirect to the sign-in page.
    """


def session_ended_response() -> Response:
    return redirect(
        url_for(
            "home_view.logout",
            error_title=SESSION_ENDED_TITLE,
            error_message=SESSION_ENDED_MESSAGE,
        )
    )


def get_token(username: str, password: str) -> Optional[Response]:
    """Sign in to Jamf Pro with the login form's credentials.

    The password is used for this one request and is never stored. Only
    the bearer token and its expiry go into the session.
    """
    # Clear any prior token up front so a failed fetch can never leave a
    # stale token from an earlier (real) login behind — that stale token
    # was the crux of the bogus-credential bypass: _validate_credentials
    # only checks that session["token"] is truthy.
    session.pop("token", None)
    session.pop("expires", None)
    try:
        basic = base64.b64encode(f"{username}:{password}".encode()).decode()
        resp = requests.post(
            f"{session['url']}/api/v1/auth/token",
            headers={"Authorization": f"Basic {basic}"},
            timeout=30,
        )
        # Without this, a non-2xx passes: Jamf Pro answers a JSON body on
        # 401/503 too, so resp.json() succeeds and data.get("token")
        # returns None -- which was then stored and returned exactly like
        # a success, leaving _validate_credentials' truthiness check as
        # the only thing standing between a failed fetch and a session.
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token")
        expires = data.get("expires")
        if not token or not expires:
            # A 2xx carrying no token is not a token.
            raise ValueError("token response contained no token/expires")
        session["token"] = token
        session["expires"] = expires
    except requests.exceptions.Timeout as err:
        logthis.error(f"[{session.get('url')}] Token request timed out: {err}")
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Connection Timeout",
                error_message="Jamf Pro did not answer in time. Try again.",
            )
        )
    except Exception as err:
        logthis.error(
            f"[{session.get('url')}] Could not get a token for the login: {err}."
        )
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Error Fetching API Token",
                error_message="Please sign in again",
            )
        )


def _remaining(expires: Optional[str]) -> timedelta:
    """Time left on a token, or zero when the expiry is unusable."""
    try:
        return datetime.strptime(expires, _EXPIRES_FORMAT) - datetime.now(
            timezone.utc
        )
    except (TypeError, ValueError):
        return timedelta(0)


def _end_session() -> None:
    session.clear()
    raise SessionEnded()


def fresh_token(session_data: Optional[Dict[str, Any]] = None) -> str:
    """Return a live Jamf Pro bearer token, renewing it when it is near
    expiry with Jamf Pro's keep-alive endpoint.

    `session_data` is the snapshot some views take before calling a
    handler; it is updated in place so the request that follows carries
    the new token, not the old one. When the token has expired, or the
    renewal fails, the session is cleared and SessionEnded is raised.
    """
    source = session_data if session_data is not None else session
    token = source.get("token") or session.get("token")
    expires = source.get("expires") or session.get("expires")
    if not token:
        _end_session()

    remaining = _remaining(expires)
    if remaining <= timedelta(0):
        logthis.warning(
            f"[{session.get('url')}] API token expired; the admin must sign in again."
        )
        _end_session()

    if remaining <= RENEW_MARGIN:
        try:
            resp = requests.post(
                f"{session['url']}/api/v1/auth/keep-alive",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            token, expires = data.get("token"), data.get("expires")
            if not token or not expires:
                raise ValueError("keep-alive response contained no token")
        except Exception as err:
            logthis.error(
                f"[{session.get('url')}] Could not renew the API token: {err}"
            )
            _end_session()
        session["token"] = token
        session["expires"] = expires

    if session_data is not None:
        session_data["token"] = token
        session_data["expires"] = expires
    return token


def validate_token(expires: str) -> bool:
    time_to_expire = datetime.strptime(
        expires, "%Y-%m-%dT%H:%M:%S.%f%z"
    ) - datetime.strptime(
        str(datetime.now(timezone.utc)), "%Y-%m-%d %H:%M:%S.%f%z"
    )
    if time_to_expire > timedelta(0):
        return True
    else:
        logthis.warning(
            f"[{session.get('url')}] API token expired ({time_to_expire}). Attempting to fetch new token..."
        )
        return False


def invalidate_token() -> None:
    if not session.get("token"):
        return
    try:
        resp = requests.post(
            f"{session['url']}/api/v1/auth/invalidate-token",
            headers={"Authorization": f"Bearer {session.get('token')}"},
            timeout=30,
        )
    except Exception as err:
        logthis.error(
            f"[{session.get('url')}] Error accessing Jamf Pro API endpoint for token invalidation. {err}"
        )
        return
    if resp.status_code == 204:
        logthis.info(
            f"[{session.get('url')}] Successfully invalidated token for logout."
        )
    elif resp.status_code == 401:
        logthis.info(
            f"[{session.get('url')}] Token is already invalid.  Logging out."
        )
    else:
        logthis.info(
            f"[{session.get('url')}] An unknown error occurred when invalidating the token."
        )
