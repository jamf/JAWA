#!/usr/bin/env python3
"""Update mobile device extension attribute from webhook event.

Handles both Jamf Pro standard webhook events and custom JSON posts.
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


def build_ea_xml(ea_name, value):
    return (
        f"<mobile_device><extension_attributes><extension_attribute>"
        f"<name>{ea_name}</name><value>{value}</value>"
        f"</extension_attribute></extension_attributes></mobile_device>"
    )


def main():
    config = Config()
    event_data = json.loads(sys.argv[1])

    # Support both custom and standard webhook formats
    if "DeviceID" in event_data:
        # Custom webhook format
        device_id = event_data["DeviceID"]
        ea_name = event_data["EaName"]
        value = event_data["Value"]
    else:
        # Standard Jamf Pro webhook
        device_id = event_data["event"]["jssID"]
        ea_name = "Last Webhook Action"
        value = event_data["webhook"]["webhookEvent"]

    # Build XML and send PUT
    xml_data = build_ea_xml(ea_name, value)
    token = get_oauth_token()
    resp = requests.put(
        f"{config.server_url}/JSSResource/mobiledevices/id/{device_id}",
        headers={
            "Content-Type": "application/xml",
            "Authorization": f"Bearer {token}",
        },
        data=xml_data,
        timeout=30,
    )
    resp.raise_for_status()
    print(f"Updated EA '{ea_name}' = '{value}' for device {device_id}")


if __name__ == "__main__":
    main()
