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
from typing import Any, Dict, List, Union

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

blueprint = Blueprint(
    "credential_view",
    __name__,
    template_folder="../templates",
)

logthis = logger.setup_child_logger("jawa", "credential_view")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "data", "credentials.json")

ERROR_TITLE = "Session Timed Out"
ERROR_MSG_SIGN_IN = "Please sign in again"
LOGOUT_ENDPOINT = "home_view.logout"


def _load_credentials() -> List[Dict[str, Any]]:
    """Load saved credential sets."""
    if not os.path.isfile(CREDENTIALS_FILE):
        return []
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_credentials(credentials: List[Dict[str, Any]]) -> None:
    """Save credential sets to file."""
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)


@blueprint.route("/setup/credentials", methods=["GET"])
def credentials_page() -> Union[Response, str]:
    """Credential management page."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    credentials = _load_credentials()
    return render_template(
        "setup/credentials.html",
        username=session.get("username"),
        credentials=credentials,
    )


@blueprint.route("/setup/credentials/add", methods=["POST"])
def add_credential() -> Response:
    """Add a new credential set."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    name = str(escape(request.form.get("name", "").strip()))
    server_url = str(escape(request.form.get("server_url", "").strip()))
    client_id = str(escape(request.form.get("client_id", "").strip()))
    client_secret = request.form.get("client_secret", "").strip()

    if not name:
        return redirect(
            url_for(
                "error",
                error="Invalid Input",
                error_message="Credential name is required.",
            )
        )

    credentials = _load_credentials()
    credentials.append(
        {
            "name": name,
            "server_url": server_url,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )
    _save_credentials(credentials)

    logthis.info(
        f"[{session.get('url')}] {session.get('username')} "
        f"added credential set: {name}"
    )

    return redirect(url_for("credential_view.credentials_page"))


@blueprint.route("/setup/credentials/delete/<int:index>", methods=["POST"])
def delete_credential(index: int) -> Response:
    """Delete a credential set by index."""
    if "username" not in session:
        return redirect(
            url_for(
                LOGOUT_ENDPOINT,
                error_title=ERROR_TITLE,
                error_message=ERROR_MSG_SIGN_IN,
            )
        )

    credentials = _load_credentials()
    if 0 <= index < len(credentials):
        removed = credentials.pop(index)
        _save_credentials(credentials)
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} "
            f"deleted credential set: {removed.get('name')}"
        )

    return redirect(url_for("credential_view.credentials_page"))
