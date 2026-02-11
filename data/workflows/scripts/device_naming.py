#!/usr/bin/env python3
"""Auto-rename mobile devices by asset tag on enrollment.

Webhook event: MobileDeviceEnrolled
API privileges: Read Mobile Devices, Send Mobile Device Set Device Name Command
"""

import json
import logging
import requests
import sys
import time

token_cache = {"access_token": None, "expires_in": 0, "timestamp": 0}


class Config:
    def __init__(self):
        self.server_url = "https://example.jamfcloud.com"  # Your Jamf Pro URL
        self.token_url = f"{self.server_url}/api/oauth/token"
        self.client_id = "your_client_id"
        self.client_secret = "your_client_secret"
        self.scope = ""  # e.g., api-role:5


def get_oauth_token():
    global token_cache
    current_time = time.time()
    config = Config()
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
    )
    response_data = response.json()
    token_cache = {
        "access_token": response_data["access_token"],
        "expires_in": response_data["expires_in"],
        "timestamp": current_time,
    }
    return token_cache["access_token"]


def api_get(endpoint):
    config = Config()
    token = get_oauth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = requests.get(
        f"{config.server_url}/JSSResource/{endpoint}", headers=headers
    )
    resp.raise_for_status()
    return resp.json()


def api_post(endpoint):
    config = Config()
    token = get_oauth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = requests.post(
        f"{config.server_url}/JSSResource/{endpoint}", headers=headers
    )
    resp.raise_for_status()
    return resp


def main():
    # 1. Parse webhook event
    try:
        event_data = json.loads(sys.argv[1])
    except (json.JSONDecodeError, IndexError) as err:
        print(f"Error parsing webhook JSON: {err}")
        sys.exit(1)

    event = event_data["event"]
    jss_id = str(event["jssID"])
    old_name = event.get("deviceName", "Unknown")
    serial = event.get("serialNumber", "Unknown")
    room = event.get("room", "")

    # 2. Filter: skip bedside devices (those with room assignments)
    if room:
        print(f"Device has room assignment ({room}) - skipping rename.")
        sys.exit(5)

    # 3. Wait for device record to populate, then look up asset tag
    time.sleep(30)
    try:
        device_record = api_get(f"mobiledevices/id/{jss_id}")
        asset_tag = device_record["mobile_device"]["general"].get("asset_tag")
    except Exception as err:
        print(f"Could not GET device record for ID {jss_id}: {err}")
        sys.exit(2)

    if not asset_tag:
        print(f"No asset tag for ID {jss_id}. Exiting.")
        sys.exit(3)

    # 4. Send DeviceName command
    try:
        api_post(
            f"mobiledevicecommands/command/DeviceName/{asset_tag}/id/{jss_id}"
        )
        print(
            f"Renamed {old_name} -> {asset_tag} (SN: {serial}, ID: {jss_id})"
        )
    except Exception as err:
        print(f"Failed to rename device ID {jss_id}: {err}")
        sys.exit(4)

    # 5. Send blank push to speed up command delivery
    try:
        api_post(f"mobiledevicecommands/command/BlankPush/id/{jss_id}")
    except Exception:
        pass  # Non-critical


if __name__ == "__main__":
    main()
