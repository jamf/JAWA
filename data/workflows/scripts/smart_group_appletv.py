#!/usr/bin/env python3
"""Restart Apple TVs that join a smart group.

Webhook event: SmartGroupMobileDeviceMembershipChange
API privileges: Send Mobile Device Restart Device Command,
                Send Mobile Device Update Inventory Command
"""

import json
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


def main():
    try:
        event_data = json.loads(sys.argv[1])
    except (json.JSONDecodeError, IndexError) as err:
        print(f"Error parsing webhook JSON: {err}")
        sys.exit(1)

    id_list = event_data.get("event", {}).get("groupAddedDevicesIds", [])
    if not id_list:
        print("No devices entered the group.")
        sys.exit(12)

    for jss_id in id_list:
        print(f"Restarting device ID {jss_id}...")
        # Apple TVs need time to become responsive after joining.
        time.sleep(200)
        try:
            perform_api_call(
                f"mobiledevicecommands/command/RestartDevice/id/{jss_id}",
                method="POST",
            )
            time.sleep(10)
            perform_api_call(
                f"mobiledevicecommands/command/UpdateInventory/id/{jss_id}",
                method="POST",
            )
            print(f"Device {jss_id}: restart and inventory queued.")
        except Exception as err:
            print(f"Device {jss_id}: command failed: {err}")
            sys.exit(4)


if __name__ == "__main__":
    main()
