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

from datetime import datetime, timezone, timedelta
from flask import Response, session, redirect, url_for
import requests
from typing import Optional

from bin import logger

logthis = logger.setup_child_logger("jawa", __name__)


def get_token() -> Optional[Response]:
    try:
        resp = requests.post(
            f"{session['url']}/api/v1/auth/token",
            headers={"Authorization": f"Basic {session['b64_auth'].decode()}"},
        )
        data = resp.json()
        session["token"] = data.get("token")
        session["expires"] = data.get("expires")
    except Exception as err:
        logthis.info(
            f"[{session.get('url')}] Could not get a token using session credentials: {err}.  Logging out."
        )
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Error Fetching API Token",
                error_message="Please sign in again",
            )
        )


def validate_token(expires: str) -> bool:
    time_to_expire = datetime.strptime(
        expires, "%Y-%m-%dT%H:%M:%S.%f%z"
    ) - datetime.strptime(
        str(datetime.now(timezone.utc)), "%Y-%m-%d %H:%M:%S.%f%z"
    )
    if time_to_expire > timedelta(0):
        return True
    else:
        logthis.info(
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
        )
    except Exception as err:
        logthis.info(
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
