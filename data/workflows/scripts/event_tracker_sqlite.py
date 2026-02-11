#!/usr/bin/env python3
"""Track webhook events in a SQLite database with cooldown logic.

Webhook event: ComputerCheckIn, MobileDeviceCheckIn
API privileges: None (logging only)
"""

import datetime
import json
import sqlite3
import sys

DB_PATH = "placeholder_value"  # Path to SQLite database file
COOLDOWN_HOURS = 12  # Hours between recording repeat check-ins


def create_check_in_db(db_path):
    """Create SQLite database for check-in tracking."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS check_in_stats (
        jps_id INTEGER NOT NULL PRIMARY KEY,
        serial_number TEXT NOT NULL,
        device_name TEXT,
        last_check_in TEXT NOT NULL,
        total_check_ins INTEGER NOT NULL DEFAULT 1
    )""")
    conn.commit()
    return conn


def record_check_in(
    conn, jss_id, serial, device_name, event_time, cooldown_hours=12
):
    """Record a device check-in with cooldown logic.

    Returns True if the check-in was recorded (outside cooldown).
    Returns False if within cooldown window.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT last_check_in, total_check_ins FROM check_in_stats WHERE jps_id=?",
        (jss_id,),
    )
    row = cur.fetchone()

    if not row:
        conn.execute(
            "INSERT INTO check_in_stats "
            "(jps_id, serial_number, device_name, last_check_in, total_check_ins) "
            "VALUES (?, ?, ?, ?, 1)",
            (jss_id, serial, device_name, event_time),
        )
        conn.commit()
        return True

    last_time = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    current_time = datetime.datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S")
    delta = current_time - last_time
    total = row[1]

    if delta.total_seconds() >= (cooldown_hours * 3600):
        conn.execute(
            "UPDATE check_in_stats SET last_check_in=?, total_check_ins=?, "
            "device_name=? WHERE jps_id=?",
            (event_time, total + 1, device_name, jss_id),
        )
        conn.commit()
        print(
            f"  {device_name}: check-in recorded (total: {total + 1}, delta: {delta})"
        )
        return True
    else:
        conn.execute(
            "UPDATE check_in_stats SET total_check_ins=? WHERE jps_id=?",
            (total + 1, jss_id),
        )
        conn.commit()
        print(
            f"  {device_name}: within cooldown ({delta} < {cooldown_hours}h)"
        )
        return False


def main():
    # 1. Parse webhook event
    try:
        event_data = json.loads(sys.argv[1])
    except (json.JSONDecodeError, IndexError) as err:
        print(f"Error parsing webhook JSON: {err}")
        sys.exit(1)

    event = event_data.get("event", {})
    jss_id = event.get("jssID") or event.get("computer", {}).get("jssID")
    serial = event.get("serialNumber", "Unknown")
    device_name = event.get("deviceName") or event.get("computer", {}).get(
        "deviceName", "Unknown"
    )

    if not jss_id:
        print("No device ID found in event data.")
        sys.exit(2)

    event_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Open database and record
    conn = create_check_in_db(DB_PATH)
    recorded = record_check_in(
        conn, jss_id, serial, device_name, event_time, COOLDOWN_HOURS
    )
    conn.close()

    if recorded:
        print(f"Check-in recorded for {device_name} (ID: {jss_id})")
    else:
        print(f"Check-in within cooldown for {device_name} (ID: {jss_id})")


if __name__ == "__main__":
    main()
