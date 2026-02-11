#!/usr/bin/env python3
"""Send Slack notification on smart group membership change.

Webhook event: SmartGroupComputerMembershipChange
"""

import json
import requests
import sys
from datetime import datetime

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"


def main():
    event_data = json.loads(sys.argv[1])
    event = event_data["event"]

    id_list = event.get("groupAddedDevicesIds", [])
    if not id_list:
        print("No devices entered the group.")
        sys.exit(12)

    group_name = event.get("name", "Unknown Group")
    _device_names = event.get("groupAddedDevices", [])

    slack_data = {
        "attachments": [
            {
                "color": "#056ae6",
                "title": f"Smart Group Update: {group_name}",
                "text": f"{len(id_list)} device(s) added to {group_name}",
                "footer": "JAWA Webhook Automation",
                "ts": datetime.timestamp(datetime.now()),
            }
        ]
    }

    resp = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps(slack_data),
        headers={"Content-Type": "application/json"},
    )
    print(f"Slack notification: {resp.status_code}")


if __name__ == "__main__":
    main()
