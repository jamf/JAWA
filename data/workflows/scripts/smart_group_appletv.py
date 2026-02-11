#!/usr/bin/env python3
"""Restart Apple TVs that join a smart group.

Webhook event: SmartGroupMobileDeviceMembershipChange
"""

import json
import requests
import sys
import time

# ... (Config, OAuth, perform_api_call from foundations) ...


def main():
    event_data = json.loads(sys.argv[1])
    id_list = event_data["event"]["groupAddedDevicesIds"]

    if not id_list:
        print("No devices entered the group.")
        sys.exit(12)

    for jss_id in id_list:
        print(f"Restarting device ID {jss_id}...")
        time.sleep(200)  # Wait for Apple TV to be responsive
        perform_api_call(
            f"mobiledevicecommands/command/RestartDevice/id/{jss_id}",
            method="POST",
        )
        time.sleep(10)
        perform_api_call(
            f"mobiledevicecommands/command/UpdateInventory/id/{jss_id}",
            method="POST",
        )


if __name__ == "__main__":
    main()
