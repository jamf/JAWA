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
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from bin import logger

logthis = logger.setup_child_logger("jawa", "data_store")

_base_dir = os.path.dirname(os.path.dirname(__file__))

WEBHOOKS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "webhooks.json")
)
CRON_FILE = os.path.abspath(os.path.join(_base_dir, "data", "cron.json"))
SERVER_FILE = os.path.abspath(os.path.join(_base_dir, "data", "server.json"))
TIME_FILE = os.path.abspath(os.path.join(_base_dir, "data", "time.json"))
WEBHOOK_SCHEMAS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "webhook_schemas.json")
)
SCRIPTS_DIR = os.path.abspath(os.path.join(_base_dir, "scripts"))


# --- Low-level I/O ---


def _read_json(filepath: str, default: Any = None) -> Any:
    if default is None:
        default = []
    if not os.path.isfile(filepath):
        with open(filepath, "w") as f:
            json.dump(default, f)
        return default
    with open(filepath, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def _write_json(filepath: str, data: Any) -> None:
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)


# --- Webhooks ---


def get_all_webhooks() -> List[Dict]:
    return _read_json(WEBHOOKS_FILE)


def get_webhooks_by_tag(tag: str) -> List[Dict]:
    return [w for w in get_all_webhooks() if w.get("tag") == tag]


def get_webhook_by_name(name: str) -> Optional[Dict]:
    for w in get_all_webhooks():
        if w.get("name") == name:
            return w
    return None


def webhook_name_exists(name: str) -> bool:
    return any(w.get("name") == name for w in get_all_webhooks())


def add_webhook(entry: Dict) -> None:
    data = get_all_webhooks()
    data.append(entry)
    _write_json(WEBHOOKS_FILE, data)


def update_webhook_in_list(
    webhooks: List[Dict], name: str, updates: Dict
) -> None:
    """Update a webhook entry in an already-loaded list (in-place)."""
    for w in webhooks:
        if w.get("name") == name:
            w.update(updates)
            break


def save_all_webhooks(data: List[Dict]) -> None:
    _write_json(WEBHOOKS_FILE, data)


def remove_webhook(name: str) -> Optional[Dict]:
    data = get_all_webhooks()
    removed = None
    for w in data:
        if w.get("name") == name:
            removed = dict(w)
            data.remove(w)
            break
    _write_json(WEBHOOKS_FILE, data)
    return removed


# --- Crons ---


def get_all_crons() -> List[Dict]:
    return _read_json(CRON_FILE)


def get_cron_by_name(name: str) -> Optional[Dict]:
    for c in get_all_crons():
        if c.get("name") == name:
            return c
    return None


def cron_name_exists(name: str) -> bool:
    return any(c.get("name") == name for c in get_all_crons())


def add_cron(entry: Dict) -> None:
    data = get_all_crons()
    data.append(entry)
    _write_json(CRON_FILE, data)


def save_all_crons(data: List[Dict]) -> None:
    _write_json(CRON_FILE, data)


def remove_cron(name: str) -> Optional[Dict]:
    data = get_all_crons()
    removed = None
    for c in data:
        if c.get("name") == name:
            removed = dict(c)
            data.remove(c)
            break
    _write_json(CRON_FILE, data)
    return removed


# --- Server Config ---


def get_server_config() -> Dict:
    if not os.path.isfile(SERVER_FILE):
        return {}
    with open(SERVER_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def get_jawa_address() -> Optional[str]:
    return get_server_config().get("jawa_address")


def get_time_data() -> Dict:
    with open(TIME_FILE, "r") as f:
        return json.load(f)


def get_webhook_schemas() -> Dict[str, Any]:
    """Read the static Jamf Pro webhook event catalog.

    Hand-maintained reference data, not runtime state: the file ships
    with JAWA and is edited directly when Jamf Pro's event set changes.
    Read on every call (it is small, and no caching keeps a stale copy
    alive after an edit). Degrades to empty structures instead of
    raising, because the Jamf automation form's event dropdown reads
    this too and must still render if the file is damaged.
    """
    empty: Dict[str, Any] = {
        "categories": {},
        "schemas": {},
        "examples": {},
    }
    try:
        with open(WEBHOOK_SCHEMAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        # ValueError covers both a malformed JSON body
        # (json.JSONDecodeError) and a file saved in a non-UTF-8
        # encoding (UnicodeDecodeError) - neither is an OSError.
        logthis.warning(
            f"Webhook event catalog unreadable: {WEBHOOK_SCHEMAS_FILE}"
        )
        return empty
    if not isinstance(data, dict):
        logthis.warning("Webhook event catalog is not a JSON object.")
        return empty
    # Each section is iterated as a mapping by the reference pages and
    # the event dropdown, so a hand edit that turns one into a list or
    # a string degrades to empty here rather than failing in a template.
    out: Dict[str, Any] = {}
    for key in empty:
        section = data.get(key)
        out[key] = section if isinstance(section, dict) else {}
    return out


# --- Script Management ---


def save_script(
    file_storage: Any, name_prefix: str, separator: str = "-"
) -> str:
    """Save an uploaded script with a prefixed filename.

    Returns the absolute path to the saved file.
    """
    # A JAWA automation script is executed directly by the receiver
    # (Popen, argv form). Without a shebang the OS cannot pick an
    # interpreter, so it would fail cryptically at trigger time. Reject
    # it here so the upload fails clearly instead.
    head = file_storage.read(2)
    file_storage.seek(0)
    if head != b"#!":
        raise ValueError(
            "Script must start with a shebang (e.g. #!/bin/bash)."
        )
    if not os.path.isdir(SCRIPTS_DIR):
        os.mkdir(SCRIPTS_DIR)
    filename = file_storage.filename
    if " " in filename:
        filename = filename.replace(" ", "-")
    new_filename = f"{name_prefix}{separator}{filename}"
    safe_name = secure_filename(new_filename)
    filepath = os.path.join(SCRIPTS_DIR, safe_name)
    file_storage.save(filepath)
    os.chmod(filepath, mode=0o0755)
    return filepath


def retire_script(path: str) -> None:
    """Rename a script to .old instead of deleting it."""
    if os.path.exists(path):
        os.rename(path, f"{path}.old")
