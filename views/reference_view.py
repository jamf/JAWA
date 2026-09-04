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

from typing import Union

from flask import Blueprint, Response, abort, render_template

from bin import logger
from bin.auth import login_required
from bin.data_store import get_webhook_schemas

logthis = logger.setup_child_logger("jawa", "reference_view")

blueprint = Blueprint("reference", __name__)


def _context(selected_event: Union[str, None]) -> dict:
    catalog = get_webhook_schemas()
    return {
        "categories": catalog["categories"],
        "schemas": catalog["schemas"],
        "examples": catalog["examples"],
        "selected_event": selected_event,
    }


@blueprint.route("/reference/webhooks")
@login_required
def webhooks() -> Union[Response, str]:
    """Overview of every Jamf Pro webhook event, grouped by category."""
    return render_template("reference/webhooks.html", **_context(None))


@blueprint.route("/reference/webhooks/<event_type>")
@login_required
def webhook_detail(event_type: str) -> Union[Response, str]:
    """Field schema and sample payload for one Jamf Pro event."""
    context = _context(event_type)
    if event_type not in context["schemas"]:
        logthis.info(f"Unknown webhook event requested: {event_type}")
        abort(404)
    return render_template("reference/webhooks.html", **context)
