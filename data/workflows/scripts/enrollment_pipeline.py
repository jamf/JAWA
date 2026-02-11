#!/usr/bin/env python3
"""Multi-step enrollment pipeline.

Supports multiple webhook trigger events:
  - MobileDeviceEnrolled (single device)
  - ComputerAdded (single device)
  - SmartGroupMobileDeviceMembershipChange (batch of devices)
"""

import csv, json, logging, requests, sys, time

# ... (Config, OAuth, perform_api_call from foundations) ...

CSV_FILE = "/usr/local/JAWA/resources/files/DeviceAssignments.csv"


def extract_device_ids(event_data):
    """Extract device ID(s) from any supported webhook event type."""
    event = event_data.get("event", {})
    webhook_event = event_data.get("webhook", {}).get("webhookEvent", "")

    # Smart group events provide a list of added device IDs
    if "SmartGroup" in webhook_event:
        ids = event.get("groupAddedDevicesIds", [])
        return [int(i) for i in ids] if ids else []

    # Enrollment and add events provide a single device ID
    jss_id = event.get("jssID")
    if jss_id:
        return [int(jss_id)]

    return []


def main():
    # Stage 1-2: Parse event
    event_data = json.loads(sys.argv[1])
    id_list = extract_device_ids(event_data)
    if not id_list:
        sys.exit(12)

    for jss_id in id_list:
        # Stage 3: Get device serial, match to CSV
        time.sleep(30)
        device = api_get(f"api/v2/mobile-devices/{jss_id}/detail")
        serial = device.get("serialNumber")
        model = device.get("model", "")

        # Apple TV fork
        if "appletv" in model.lower():
            handle_apple_tv(jss_id, serial)
            continue

        assignment = lookup_csv(serial, CSV_FILE)
        if not assignment:
            print(f"{serial} not in spreadsheet.")
            continue

        # Stage 4: Update device record
        update_record(jss_id, assignment)

        # Stage 5: Queue commands
        set_device_name(jss_id, assignment["name"])

        # Stage 6: Poll for DeviceConfigured
        completed = poll_command(jss_id, "DeviceConfigured")

        if completed:
            print(f"ID {jss_id} ({serial}) completed setup.")
        else:
            print(f"ID {jss_id} ({serial}) failed - erasing.")
            send_erase(jss_id)


if __name__ == "__main__":
    main()
