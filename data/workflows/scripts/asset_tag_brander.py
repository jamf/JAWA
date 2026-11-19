#!/usr/bin/env python3
"""Brander (Asset Tag Watch): re-brand a device when its asset tag changes.

Trigger: JAWA timed automation (cron), every 15 minutes by default.
Brander templates print the device's asset tag, so a re-tagged device
keeps showing its old tag until someone re-brands it. This watches
every Jamf Pro mobile device and runs the installed Brander (Tap Action)
script for each device whose asset tag or "Brander" extension
attribute changed since the last run.

- The asset tag is the first non-empty of asset_tag, barcode_1 and
  barcode_2. null, none, n/a and blank count as empty.
- State lives in a SQLite file. A device seen for the first time is
  recorded and not branded, so the first run only seeds.
- A device's new values are stored only once its brand attempt is
  handled: Brander exit 0, 42 (Brander EA Off), 25 (not supervised) or
  26 (not iOS or iPadOS). Any other exit, or a timeout, leaves the
  stored values alone so the next run tries again.
- With dry run on, it prints what it would brand and changes nothing
  for changed devices.

Exit codes: 0 done; 1 the device list could not be fetched (nothing
stored); 2 at least one brand attempt was not handled.
"""

import datetime
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time

import requests

# --- JAWA canonical Jamf API block (keep identical across templates) ---

token_cache = {"access_token": None, "expires_in": 0, "timestamp": 0}


class Config:
    def __init__(self):
        self.server_url = "__JAWA_SERVER_URL__"
        self.token_url = f"{self.server_url}/api/oauth/token"
        self.client_id = "__JAWA_CLIENT_ID__"
        self.client_secret = "__JAWA_CLIENT_SECRET__"
        self.scope = ""


def get_oauth_token():
    """Fetch (and cache) an OAuth access token from Jamf Pro."""
    global token_cache
    config = Config()
    current_time = time.time()
    if (
        token_cache["access_token"]
        and (current_time - token_cache["timestamp"])
        < token_cache["expires_in"]
    ):
        return token_cache["access_token"]
    data = {
        "client_id": config.client_id,
        "grant_type": "client_credentials",
        "client_secret": config.client_secret,
    }
    if config.scope:
        data["scope"] = config.scope
    response = requests.post(
        config.token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )
    response.raise_for_status()
    response_data = response.json()
    token_cache = {
        "access_token": response_data["access_token"],
        "expires_in": response_data["expires_in"],
        "timestamp": current_time,
    }
    return token_cache["access_token"]


def perform_api_call(endpoint, method="GET", data=None, api="classic"):
    """Call the Jamf Pro API and return the parsed response.

    endpoint: path with no leading slash, e.g. "mobiledevices/id/42".
    api: "classic" for /JSSResource, "pro" for /api.
    Returns parsed JSON, or the raw response when the body is not JSON.
    """
    config = Config()
    token = get_oauth_token()
    prefix = "JSSResource" if api == "classic" else "api"
    url = f"{config.server_url}/{prefix}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method, url, headers=headers, json=data, timeout=30
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response

# --- end canonical block ---


# Template settings (filled in when the template is enabled).
DB_PATH = "__JAWA_DB_PATH__"
BRANDER_SCRIPT = "__JAWA_BRANDER_SCRIPT__"
DRY_RUN = "__JAWA_DRY_RUN__"  # "yes" to report only

BRANDER_TIMEOUT = 300  # seconds per device
# Brander exits that settle a change: branded, or a device Brander will
# never brand as it stands. Anything else is retried on the next run.
HANDLED_EXITS = {
    0: "branded",
    25: "not supervised",
    26: "not iOS or iPadOS",
    42: "Brander EA is Off",
}
EMPTY_VALUES = ("", "null", "none", "n/a")
ASSET_TAG_FIELDS = ("asset_tag", "barcode_1", "barcode_2")


def clean(value):
    """A watched value, or None when it is empty in any spelling."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in EMPTY_VALUES else text


def asset_tag(general):
    for field in ASSET_TAG_FIELDS:
        value = clean(general.get(field))
        if value is not None:
            return value
    return None


def brander_ea(device):
    for ea in device.get("extension_attributes") or []:
        if isinstance(ea, dict) and ea.get("name") == "Brander":
            return clean(ea.get("value"))
    return None


def open_db(path):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS asset_and_ea_tracking (
        jps_id INTEGER NOT NULL PRIMARY KEY,
        serial_number TEXT NOT NULL,
        device_name TEXT,
        current_asset_tag TEXT,
        previous_asset_tag TEXT,
        current_brander_ea TEXT,
        previous_brander_ea TEXT,
        last_checked_timestamp DATETIME NOT NULL,
        last_change_timestamp DATETIME,
        asset_tag_change_count INTEGER DEFAULT 0,
        brander_ea_change_count INTEGER DEFAULT 0,
        total_change_count INTEGER DEFAULT 0
    )""")
    conn.commit()
    return conn


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_device_ids():
    """Every mobile device id, or None when Jamf Pro cannot be read."""
    try:
        listing = perform_api_call("mobiledevices")
        return [int(d["id"]) for d in listing["mobile_devices"]]
    except requests.RequestException as err:
        print(f"Could not list mobile devices: {type(err).__name__}.")
    except (KeyError, TypeError, ValueError):
        print("Jamf Pro's mobile device list was not in the expected shape.")
    return None


def read_device(jps_id):
    """The watched fields of one device, or None when it cannot be read."""
    try:
        record = perform_api_call(f"mobiledevices/id/{jps_id}")
    except requests.RequestException as err:
        print(f"device {jps_id}: could not be read ({type(err).__name__}).")
        return None
    device = record.get("mobile_device") if isinstance(record, dict) else None
    if not isinstance(device, dict):
        print(f"device {jps_id}: record was not in the expected shape.")
        return None
    general = device.get("general") or {}
    return {
        "jps_id": jps_id,
        "serial_number": str(general.get("serial_number") or ""),
        "device_name": general.get("device_name") or "",
        "udid": str(general.get("udid") or "").strip(),
        "asset_tag": asset_tag(general),
        "brander_ea": brander_ea(device),
    }


def brand(device):
    """Run Brander for one device. True when the attempt is handled."""
    jps_id = device["jps_id"]
    if not os.path.isfile(BRANDER_SCRIPT):
        print(f"device {jps_id}: Brander script not found at {BRANDER_SCRIPT}.")
        return False
    if not device["udid"]:
        print(f"device {jps_id}: the Jamf Pro record has no UDID; not branded.")
        return False
    payload = json.dumps({"event": {"jssID": jps_id, "udid": device["udid"]}})
    try:
        result = subprocess.run(
            [sys.executable, BRANDER_SCRIPT, payload],
            capture_output=True,
            text=True,
            timeout=BRANDER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"device {jps_id}: Brander took over {BRANDER_TIMEOUT}s; will retry.")
        return False
    except OSError as err:
        print(f"device {jps_id}: Brander could not start ({type(err).__name__}).")
        return False
    lines = (result.stdout or "").strip().splitlines()
    said = f": {lines[-1]}" if lines else ""
    code = result.returncode
    if code in HANDLED_EXITS:
        print(f"device {jps_id}: Brander exit {code}, {HANDLED_EXITS[code]}{said}")
        return True
    print(f"device {jps_id}: Brander exit {code}, will retry{said}")
    return False


def store_change(conn, device, stored_tag, stored_ea):
    tag_changed = device["asset_tag"] != stored_tag
    ea_changed = device["brander_ea"] != stored_ea
    stamp = now()
    conn.execute(
        """UPDATE asset_and_ea_tracking SET
            previous_asset_tag = CASE WHEN ? THEN current_asset_tag
                                      ELSE previous_asset_tag END,
            current_asset_tag = ?,
            previous_brander_ea = CASE WHEN ? THEN current_brander_ea
                                       ELSE previous_brander_ea END,
            current_brander_ea = ?,
            device_name = ?, serial_number = ?,
            last_checked_timestamp = ?, last_change_timestamp = ?,
            asset_tag_change_count = asset_tag_change_count + ?,
            brander_ea_change_count = brander_ea_change_count + ?,
            total_change_count = total_change_count + ?
        WHERE jps_id = ?""",
        (
            tag_changed, device["asset_tag"], ea_changed, device["brander_ea"],
            device["device_name"], device["serial_number"], stamp, stamp,
            int(tag_changed), int(ea_changed), int(tag_changed) + int(ea_changed),
            device["jps_id"],
        ),
    )
    conn.commit()


def describe(device, stored_tag, stored_ea):
    changes = []
    if device["asset_tag"] != stored_tag:
        changes.append(f"asset tag '{stored_tag or ''}' -> '{device['asset_tag'] or ''}'")
    if device["brander_ea"] != stored_ea:
        changes.append(f"Brander EA '{stored_ea or ''}' -> '{device['brander_ea'] or ''}'")
    return f"device {device['jps_id']}: " + ", ".join(changes)


def hold_run_lock(db_path):
    """An exclusive lock beside the state database, or None when another
    run still holds it. A run over a large fleet, or a bulk re-tag that
    brands many devices, can outlast the schedule; two overlapping runs
    would brand the same devices twice. The lock goes when the process
    exits, however it exits."""
    handle = open(db_path + ".lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def main():
    dry_run = DRY_RUN.strip().lower() in ("yes", "y", "true", "1")
    lock = hold_run_lock(DB_PATH)
    if lock is None:
        print("Asset Tag Watch: the previous run is still going; skipping this one.")
        return
    ids = list_device_ids()
    if ids is None:
        sys.exit(1)

    conn = open_db(DB_PATH)
    checked = changed = branded = failed = unreadable = 0
    for jps_id in ids:
        device = read_device(jps_id)
        if device is None:
            unreadable += 1
            continue
        checked += 1
        row = conn.execute(
            "SELECT current_asset_tag, current_brander_ea "
            "FROM asset_and_ea_tracking WHERE jps_id = ?",
            (jps_id,),
        ).fetchone()
        if row is None:
            # First sight: record it, never brand it.
            conn.execute(
                "INSERT INTO asset_and_ea_tracking (jps_id, serial_number, "
                "device_name, current_asset_tag, current_brander_ea, "
                "last_checked_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (jps_id, device["serial_number"], device["device_name"],
                 device["asset_tag"], device["brander_ea"], now()),
            )
            conn.commit()
            continue
        stored_tag, stored_ea = row
        if (device["asset_tag"], device["brander_ea"]) == (stored_tag, stored_ea):
            conn.execute(
                "UPDATE asset_and_ea_tracking SET device_name = ?, "
                "serial_number = ?, last_checked_timestamp = ? WHERE jps_id = ?",
                (device["device_name"], device["serial_number"], now(), jps_id),
            )
            conn.commit()
            continue

        changed += 1
        print(describe(device, stored_tag, stored_ea))
        if dry_run:
            print(f"device {jps_id}: dry run, would run Brander.")
            continue
        if brand(device):
            branded += 1
            store_change(conn, device, stored_tag, stored_ea)
        else:
            failed += 1
    conn.close()

    summary = (
        f"Asset Tag Watch{' (dry run)' if dry_run else ''}: {checked} devices "
        f"checked, {changed} changed, {branded} branded, {failed} failed"
    )
    if unreadable:
        summary += f", {unreadable} could not be read"
    print(summary + ".")
    if failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
