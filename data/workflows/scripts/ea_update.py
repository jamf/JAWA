#!/usr/bin/env python3
"""Update mobile device extension attribute from webhook event.

Handles both Jamf Pro standard webhook events and custom JSON posts.
"""

import json
import requests
import sys
import time

token_cache = {"access_token": None, "expires_in": 0, "timestamp": 0}


class Config:
    def __init__(self):
        self.server_url = "https://example.jamfcloud.com"
        self.token_url = f"{self.server_url}/api/oauth/token"
        self.client_id = "your_client_id"
        self.client_secret = "your_client_secret"
        self.scope = ""


def get_oauth_token():
    global token_cache
    config = Config()
    current_time = time.time()
    if (
        token_cache["access_token"]
        and (current_time - token_cache["timestamp"])
        < token_cache["expires_in"]
    ):
        return token_cache["access_token"]
    response = requests.post(
        config.token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": config.client_id,
            "grant_type": "client_credentials",
            "client_secret": config.client_secret,
        },
    )
    rd = response.json()
    token_cache = {
        "access_token": rd["access_token"],
        "expires_in": rd["expires_in"],
        "timestamp": current_time,
    }
    return token_cache["access_token"]


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
    )
    resp.raise_for_status()
    print(f"Updated EA '{ea_name}' = '{value}' for device {device_id}")


if __name__ == "__main__":
    main()
