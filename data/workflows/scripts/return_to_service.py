#!/usr/bin/env python3
"""Return to Service automation via smart group webhook.

Webhook event: SmartGroupMobileDeviceMembershipChange
When devices enter the target smart group, this script:
1. Sets an EA to track RtS status
2. Looks up the device managementId
3. Sends ERASE_DEVICE with returnToService enabled

"""

import base64
import json
import logging
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


# WiFi profile XML (base64 will be encoded at runtime)
WIFI_PAYLOAD = b"""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1"><dict>
  <key>PayloadUUID</key><string>RTS-UNIQUE-UUID</string>
  <key>PayloadType</key><string>Configuration</string>
  <key>PayloadIdentifier</key><string>RTS-UNIQUE-UUID</string>
  <key>PayloadContent</key><array><dict>
    <key>PayloadType</key><string>com.apple.wifi.managed</string>
    <key>SSID_STR</key><string>Your-WiFi-SSID</string>
    <key>AutoJoin</key><true/>
    <key>CaptiveBypass</key><true/>
  </dict></array>
</dict></plist>"""

EA_NAME = "RtS Status"


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
    response = requests.post(
        config.token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": config.client_id,
            "grant_type": "client_credentials",
            "client_secret": config.client_secret,
            "scope": config.scope,
        },
    )
    rd = response.json()
    token_cache = {
        "access_token": rd["access_token"],
        "expires_in": rd["expires_in"],
        "timestamp": current_time,
    }
    return token_cache["access_token"]


def get_headers(content_type="json"):
    token = get_oauth_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
        if content_type == "json"
        else "application/xml",
    }


def build_ea_xml(ea_name, value):
    return (
        f"<mobile_device><extension_attributes><extension_attribute>"
        f"<name>{ea_name}</name><value>{value}</value>"
        f"</extension_attribute></extension_attributes></mobile_device>"
    )


def main():
    config = Config()
    # 1. Parse event
    event_data = json.loads(sys.argv[1])
    id_list = event_data["event"]["groupAddedDevicesIds"]
    if not id_list:
        print("No devices entered the group.")
        sys.exit(12)

    # 2. Encode WiFi payload
    wifi_b64 = base64.b64encode(WIFI_PAYLOAD).decode("ascii")

    # 3. Process each device
    for jss_id in id_list:
        # Set EA to prevent re-triggering
        ea_xml = build_ea_xml(EA_NAME, "Enrolled")
        headers = get_headers("xml")
        requests.put(
            f"{config.server_url}/JSSResource/mobiledevices/id/{jss_id}",
            headers=headers,
            data=ea_xml,
        )

        # Look up managementId
        headers = get_headers()
        resp = requests.get(
            f"{config.server_url}/api/v2/mobile-devices/{jss_id}",
            headers=headers,
        )
        mgmt_id = resp.json().get("managementId")

        # Send erase with RtS
        erase_json = {
            "clientData": [{"managementId": mgmt_id}],
            "commandData": {
                "commandType": "ERASE_DEVICE",
                "preserveDataPlan": True,
                "disallowProximitySetup": False,
                "returnToService": {
                    "enabled": True,
                    "wifiProfileData": wifi_b64,
                },
            },
        }
        resp = requests.post(
            f"{config.server_url}/api/v2/mdm/commands",
            headers=get_headers(),
            json=erase_json,
        )
        resp.raise_for_status()
        print(f"Device {jss_id}: RtS command sent.")


if __name__ == "__main__":
    main()
