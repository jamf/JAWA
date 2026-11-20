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
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape

from bin import logger

blueprint = Blueprint(
    "search_view",
    __name__,
    template_folder="../templates",
)

logthis = logger.setup_child_logger("jawa", "search_view")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBHOOKS_FILE = os.path.join(BASE_DIR, "data", "webhooks.json")
CRON_FILE = os.path.join(BASE_DIR, "data", "cron.json")
WORKFLOW_CONFIG = os.path.join(
    BASE_DIR, "data", "workflows", "workflow_config.json"
)

NAVIGABLE_PAGES: List[Dict[str, str]] = [
    {
        "title": "Dashboard",
        "url": "/dashboard",
        "description": "Main dashboard",
    },
    {"title": "Webhooks", "url": "/webhooks", "description": "All webhooks"},
    {
        "title": "Jamf Pro Webhooks",
        "url": "/webhooks/jamf",
        "description": "Jamf Pro webhook management",
    },
    {
        "title": "Okta Webhooks",
        "url": "/webhooks/okta",
        "description": "Okta webhook management",
    },
    {
        "title": "Custom Webhooks",
        "url": "/webhooks/custom",
        "description": "Custom webhook management",
    },
    {
        "title": "Templates",
        "url": "/templates",
        "description": "Pre-built automation templates",
    },
    {
        "title": "Cron Jobs",
        "url": "/cron",
        "description": "Timed automations",
    },
    {
        "title": "Log",
        "url": "/log/home.html",
        "description": "Application log viewer",
    },
    {
        "title": "Files",
        "url": "/resources/files",
        "description": "Uploaded files",
    },
    {"title": "Setup", "url": "/setup", "description": "Server configuration"},
    {
        "title": "Branding",
        "url": "/branding",
        "description": "App name and icon customization",
    },
    {
        "title": "Cleanup",
        "url": "/cleanup",
        "description": "Remove old script files",
    },
    {
        "title": "Credentials",
        "url": "/setup/credentials",
        "description": "API credential management",
    },
]


TAG_URL_MAP = {
    "jamfpro": "/webhooks/jamf",
    "okta": "/webhooks/okta",
}


def _load_json_file(filepath: str) -> list:
    """Load a JSON list from a file, returning [] on error."""
    if not os.path.isfile(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _index_pages() -> List[Dict[str, Any]]:
    """Index navigable pages."""
    return [
        {
            "title": page["title"],
            "description": page.get("description", ""),
            "url": page["url"],
            "result_type": "page",
            "searchable": (
                f"{page['title']} {page.get('description', '')}".lower()
            ),
        }
        for page in NAVIGABLE_PAGES
    ]


def _index_webhooks() -> List[Dict[str, Any]]:
    """Index webhook entries."""
    results: List[Dict[str, Any]] = []
    for wh in _load_json_file(WEBHOOKS_FILE):
        name = wh.get("name", "")
        event = wh.get("event", wh.get("okta_event", ""))
        desc = wh.get("description", "")
        script = wh.get("script", "")
        tag = wh.get("tag", "custom")
        url = TAG_URL_MAP.get(tag, "/webhooks/custom")
        results.append(
            {
                "title": name,
                "description": f"{event} - {desc}" if desc else event,
                "url": url,
                "result_type": "webhook",
                "searchable": f"{name} {event} {desc} {script}".lower(),
            }
        )
    return results


def _index_crons() -> List[Dict[str, Any]]:
    """Index cron job entries."""
    results: List[Dict[str, Any]] = []
    for cron in _load_json_file(CRON_FILE):
        name = cron.get("name", "")
        freq = cron.get("frequency", "")
        desc = cron.get("description", "")
        script = cron.get("script", "")
        results.append(
            {
                "title": name,
                "description": f"{freq} - {desc}" if desc else freq,
                "url": "/cron",
                "result_type": "cron",
                "searchable": f"{name} {freq} {desc} {script}".lower(),
            }
        )
    return results


def _index_templates() -> List[Dict[str, Any]]:
    """Index template catalog entries."""
    results: List[Dict[str, Any]] = []
    for tmpl in _load_json_file(WORKFLOW_CONFIG):
        title = tmpl.get("title", "")
        desc = tmpl.get("description", "")
        tags = " ".join(tmpl.get("tags", []))
        event = tmpl.get("trigger_event") or ""
        slug = tmpl.get("slug", "")
        results.append(
            {
                "title": title,
                "description": desc,
                "url": f"/templates/{slug}",
                "result_type": "template",
                "searchable": f"{title} {desc} {tags} {event}".lower(),
            }
        )
    return results


def _build_search_index() -> List[Dict[str, Any]]:
    """Build a flat search index from all data sources."""
    return (
        _index_pages()
        + _index_webhooks()
        + _index_crons()
        + _index_templates()
    )


def _search(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Search the index for matching results."""
    index = _build_search_index()
    query_lower = query.lower()
    terms = query_lower.split()

    results: List[Dict[str, Any]] = []
    for item in index:
        searchable = item["searchable"]
        if all(term in searchable for term in terms):
            results.append(
                {
                    "title": item["title"],
                    "description": item.get("description", ""),
                    "url": item["url"],
                    "result_type": item["result_type"],
                }
            )
    return results[:limit]


@blueprint.route("/api/search")
def api_search() -> Union[Response, str]:
    """JSON search endpoint for the navbar dropdown."""
    if "username" not in session:
        return jsonify({"results": []})

    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"results": []})

    query = str(escape(query))
    results = _search(query, limit=8)
    return jsonify({"results": results})


@blueprint.route("/search")
def search_page() -> Union[Response, str]:
    """Full search results page."""
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )

    query = request.args.get("q", "").strip()
    query = str(escape(query))
    results = _search(query, limit=50) if len(query) >= 2 else []

    return render_template(
        "search_results.html",
        username=session.get("username"),
        query=query,
        results=results,
    )
