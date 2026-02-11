#!/usr/bin/env python3
"""Send Microsoft Teams notifications for Jamf Pro webhook events.

Webhook event: Any Jamf Pro webhook event
API privileges: None (outbound notification only)
"""

import json
import requests
import sys

TEAMS_WEBHOOK_URL = "placeholder_value"  # Teams incoming webhook URL


def send_teams_notification(webhook_url, title, message, facts=None):
    """Send a notification to Microsoft Teams via incoming webhook.

    Uses Adaptive Card format for rich messages.

    Args:
        webhook_url: Teams incoming webhook URL
        title: Card title
        message: Card body text
        facts: List of {"name": str, "value": str} dicts
    """
    body = [
        {
            "type": "TextBlock",
            "size": "Medium",
            "weight": "Bolder",
            "text": title,
        },
        {"type": "TextBlock", "text": message, "wrap": True},
    ]

    if facts:
        body.append({"type": "FactSet", "facts": facts})

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }

    response = requests.post(
        webhook_url,
        data=json.dumps(card),
        headers={"Content-Type": "application/json"},
    )
    return response.status_code == 200


def main():
    # 1. Parse webhook event
    try:
        event_data = json.loads(sys.argv[1])
    except (json.JSONDecodeError, IndexError) as err:
        print(f"Error parsing webhook JSON: {err}")
        sys.exit(1)

    webhook_name = event_data.get("webhook", {}).get(
        "webhookEvent", "Unknown Event"
    )
    event = event_data.get("event", {})

    # 2. Build notification details
    device_name = event.get("deviceName") or event.get("computer", {}).get(
        "deviceName", "Unknown"
    )
    serial = event.get("serialNumber") or event.get("computer", {}).get(
        "serialNumber", "Unknown"
    )
    jss_id = event.get("jssID") or event.get("computer", {}).get(
        "jssID", "Unknown"
    )

    title = f"Jamf Pro: {webhook_name}"
    message = f"Event received for device **{device_name}**."

    facts = [
        {"name": "Event", "value": webhook_name},
        {"name": "Device", "value": device_name},
        {"name": "Serial", "value": str(serial)},
        {"name": "JSS ID", "value": str(jss_id)},
    ]

    # 3. Send notification
    success = send_teams_notification(TEAMS_WEBHOOK_URL, title, message, facts)

    if success:
        print(f"Teams notification sent for {webhook_name}: {device_name}")
    else:
        print(f"Failed to send Teams notification for {webhook_name}")
        sys.exit(3)


if __name__ == "__main__":
    main()
