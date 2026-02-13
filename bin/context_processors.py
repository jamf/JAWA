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

import hashlib
import os

from flask import Flask, session


def _compute_static_hash(static_folder: str) -> str:
    """Return a short MD5 hex digest of the max mtime across all static files."""
    max_mtime = 0.0
    for root, _dirs, files in os.walk(static_folder):
        for fname in files:
            mtime = os.path.getmtime(os.path.join(root, fname))
            if mtime > max_mtime:
                max_mtime = mtime
    return hashlib.md5(str(max_mtime).encode()).hexdigest()[:10]


def register_static_cache_bust(app: Flask) -> None:
    """Append ``?v=<hash>`` to every ``url_for('static', ...)`` URL."""
    static_hash = _compute_static_hash(app.static_folder)

    @app.url_defaults
    def _add_static_hash(endpoint: str, values: dict) -> None:
        if endpoint == "static":
            values["v"] = static_hash


def inject_common_vars() -> dict:
    """Auto-inject session variables into all templates."""
    return {
        "username": session.get("username"),
        "session_url": session.get("url"),
    }
