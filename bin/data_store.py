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
import tempfile
import threading
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from bin import logger

logthis = logger.setup_child_logger("jawa", "data_store")

_base_dir = os.path.dirname(os.path.dirname(__file__))

WEBHOOKS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "webhooks.json")
)
CREDENTIALS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "credentials.json")
)
CRON_FILE = os.path.abspath(os.path.join(_base_dir, "data", "cron.json"))
SERVER_FILE = os.path.abspath(os.path.join(_base_dir, "data", "server.json"))
TIME_FILE = os.path.abspath(os.path.join(_base_dir, "data", "time.json"))
WEBHOOK_SCHEMAS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "webhook_schemas.json")
)
RUNS_FILE = os.path.abspath(os.path.join(_base_dir, "data", "runs.json"))
SCRIPTS_DIR = os.path.abspath(os.path.join(_base_dir, "scripts"))
COOLDOWNS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "tap_cooldowns.json")
)
CRON_ALERTS_FILE = os.path.abspath(
    os.path.join(_base_dir, "data", "cron_alerts.json")
)

# How many recent runs are kept for each automation.
MAX_RUNS_PER_AUTOMATION = 20
_runs_lock = threading.Lock()


# --- Low-level I/O ---


class StoreCorruptError(Exception):
    """A JSON store exists but cannot be parsed.

    Raised instead of treating the file as empty, so the next save does
    not overwrite the automations that are still recoverable on disk.
    """


_write_lock = threading.Lock()


def atomic_write_json(
    filepath: str, data: Any, indent: int = 4, private: bool = False
) -> None:
    """Write JSON through a temp file in the same folder, then rename.

    ``private`` forces owner-only (0600) permissions, for files that hold
    secrets. Otherwise the mode of the file being replaced is kept.

    The temp file is flushed and fsynced before os.replace, and the whole
    sequence runs under a process-wide lock, so a crash or a second save
    at the same moment never leaves a truncated file.
    """
    folder = os.path.dirname(os.path.abspath(filepath))
    with _write_lock:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent)
                f.flush()
                os.fsync(f.fileno())
            if private:
                os.chmod(tmp, 0o600)
            elif os.path.exists(filepath):
                os.chmod(tmp, os.stat(filepath).st_mode & 0o777)
            os.replace(tmp, filepath)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _read_json(filepath: str, default: Any = None) -> Any:
    if default is None:
        default = []
    if not os.path.isfile(filepath):
        atomic_write_json(filepath, default)
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as err:
            logthis.error(
                f"{os.path.basename(filepath)} cannot be parsed ({err}); "
                "leaving it untouched. Restore it from a backup or fix it "
                "by hand."
            )
            raise StoreCorruptError(
                f"{os.path.basename(filepath)} is corrupt"
            ) from err


def _write_json(filepath: str, data: Any, private: bool = False) -> None:
    atomic_write_json(filepath, data, private=private)


def secure_private_files(paths: Optional[List[str]] = None) -> None:
    """Make the stores that hold secrets readable by their owner only.

    Installs created these files with the service's umask (usually
    0644), so this runs at start-up to fix them in place.
    """
    for path in paths or [WEBHOOKS_FILE, CREDENTIALS_FILE]:
        try:
            if os.path.isfile(path) and os.stat(path).st_mode & 0o077:
                os.chmod(path, 0o600)
                logthis.info(f"Restricted permissions on {path} to 0600.")
        except OSError as err:
            logthis.error(f"Could not restrict permissions on {path}: {err}")


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
    _write_json(WEBHOOKS_FILE, data, private=True)


def update_webhook_in_list(
    webhooks: List[Dict], name: str, updates: Dict
) -> None:
    """Update a webhook entry in an already-loaded list (in-place)."""
    for w in webhooks:
        if w.get("name") == name:
            w.update(updates)
            break


def save_all_webhooks(data: List[Dict]) -> None:
    _write_json(WEBHOOKS_FILE, data, private=True)


def remove_webhook(name: str) -> Optional[Dict]:
    data = get_all_webhooks()
    removed = None
    for w in data:
        if w.get("name") == name:
            removed = dict(w)
            data.remove(w)
            break
    _write_json(WEBHOOKS_FILE, data, private=True)
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


# --- Run history ---


def _read_runs() -> Dict[str, List[Dict]]:
    """Run history, ignoring anything in runs.json that is not well formed."""
    data = _read_json(RUNS_FILE, {})
    if not isinstance(data, dict):
        return {}
    return {
        name: [run for run in history if isinstance(run, dict)]
        for name, history in data.items()
        if isinstance(history, list)
    }


def record_run(
    name: str,
    started: str,
    duration_s: float,
    exit_code: Optional[int],
    output_head: str,
) -> None:
    """Append one run of an automation, keeping the newest 20.

    ``exit_code`` is None when the script could not be started.
    """
    entry = {
        "started": started,
        "duration_s": round(float(duration_s), 2),
        "exit_code": exit_code,
        "output_head": output_head,
    }
    with _runs_lock:
        runs = _read_runs()
        history = runs.get(name, [])
        if not isinstance(history, list):
            history = []
        # Newest first.
        runs[name] = ([entry] + history)[:MAX_RUNS_PER_AUTOMATION]
        _write_json(RUNS_FILE, runs)


def get_runs(name: str) -> List[Dict]:
    """Recent runs of one automation, newest first."""
    history = _read_runs().get(name, [])
    return history if isinstance(history, list) else []


def get_failed_run_names() -> set:
    """Names whose most recent run did not exit 0."""
    failed = set()
    for name, history in _read_runs().items():
        if isinstance(history, list) and history:
            if history[0].get("exit_code") != 0:
                failed.add(name)
    return failed


def rename_runs(old_name: str, new_name: str) -> None:
    """Move a renamed automation's history to its new name."""
    if old_name == new_name:
        return
    with _runs_lock:
        runs = _read_runs()
        moved = runs.pop(old_name, None)
        if moved is None:
            return
        runs[new_name] = moved
        _write_json(RUNS_FILE, runs)


def clear_runs(name: str) -> None:
    with _runs_lock:
        runs = _read_runs()
        if runs.pop(name, None) is not None:
            _write_json(RUNS_FILE, runs)


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
    # Owner-only. The receiver runs this as the same `jawa` user that
    # owns it, so the group/other read bits only ever widened who could
    # read a script that may hold credentials. The shebang is left as
    # the operator wrote it -- an uploaded script may legitimately be
    # bash, and choosing its interpreter is theirs.
    os.chmod(filepath, mode=0o0700)
    return filepath


def retire_script(path: str) -> None:
    """Rename a script to .old instead of deleting it."""
    if os.path.exists(path):
        os.rename(path, f"{path}.old")


# --- Tap action cooldowns ---
#
# {service: {jss_id: last run start (unix seconds)}}. Waitress serves
# from threads in one process, so a lock makes check-and-claim atomic.

_cooldown_lock = threading.Lock()


def _cooldown_left(started: float, minutes: int, now: float) -> int:
    return max(0, int(started + minutes * 60 - now))


def tap_cooldown_remaining(
    service: str, jss_id: int, minutes: int, now: float
) -> int:
    """Seconds until this device may run this service again (0 = now)."""
    if minutes <= 0:
        return 0
    with _cooldown_lock:
        runs = _read_json(COOLDOWNS_FILE, {}).get(service, {})
    started = runs.get(str(jss_id))
    return _cooldown_left(started, minutes, now) if started else 0


def claim_tap_run(service: str, jss_id: int, minutes: int, now: float) -> int:
    """Start a run: 0 if claimed, else the seconds left to wait.

    Claimed before the script runs, so a second request arriving while
    the first is still running is refused rather than run twice.
    """
    if minutes <= 0:
        return 0
    with _cooldown_lock:
        data = _read_json(COOLDOWNS_FILE, {})
        runs = data.setdefault(service, {})
        started = runs.get(str(jss_id))
        if started and _cooldown_left(started, minutes, now):
            return _cooldown_left(started, minutes, now)
        runs[str(jss_id)] = now
        # Drop claims older than a day so the file stays small.
        for name in list(data):
            data[name] = {
                k: v for k, v in data[name].items() if now - v < 86400
            }
            if not data[name]:
                del data[name]
        _write_json(COOLDOWNS_FILE, data)
    return 0


def release_tap_run(service: str, jss_id: int) -> None:
    """Undo a claim after a failed run, so the person can retry."""
    with _cooldown_lock:
        data = _read_json(COOLDOWNS_FILE, {})
        if data.get(service, {}).pop(str(jss_id), None) is not None:
            _write_json(COOLDOWNS_FILE, data)


def clear_tap_cooldowns(service: str) -> None:
    """Admin override: every device may run the service again now."""
    with _cooldown_lock:
        data = _read_json(COOLDOWNS_FILE, {})
        if data.pop(service, None) is not None:
            _write_json(COOLDOWNS_FILE, data)


# --- Timed-run failure alerts ---


def claim_cron_alert(name: str, now: float, interval: float) -> bool:
    """True when timed automation ``name`` may send a failure alert now.

    Each cron run is its own process, so the last alert time per
    automation is kept on disk. A corrupt file counts as no previous
    alerts: it only rate-limits a chat nudge, so it is rewritten rather
    than kept. A stamp in the future (clock moved back) does not block.
    """
    try:
        data = _read_json(CRON_ALERTS_FILE, {})
    except StoreCorruptError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    last = data.get(name)
    if (
        isinstance(last, (int, float))
        and not isinstance(last, bool)
        and 0 <= now - last < interval
    ):
        return False
    data[name] = now
    _write_json(CRON_ALERTS_FILE, data)
    return True
