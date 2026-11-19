"""Saving /setup must keep server.json keys the form does not post.

The form only posts the JAWA address, the Jamf Pro URLs, the session
timeout and (sometimes) allowed admins and the failure alert URL. Other
code keeps more settings in server.json (for example ``brand``), and a
save used to drop them by rewriting the file from four keys.
"""

import json

FORM = {
    "address": "https://jawa.example.com",
    "jss-lock": "https://jamf.example.com",
    "alternate": "",
    "session_timeout_minutes": "15",
}


def test_setup_save_keeps_keys_the_form_does_not_post(
    logged_in_client, jawa_env
):
    cfg = json.loads(jawa_env.server_file.read_text())
    cfg["brand"] = {"org_name": "Example Org"}
    cfg["allowed_admins"] = ["admin"]
    cfg["failure_alert_url"] = "https://hooks.example.com/alert"
    jawa_env.server_file.write_text(json.dumps(cfg))

    logged_in_client.post("/setup", data=FORM)

    saved = json.loads(jawa_env.server_file.read_text())
    assert saved["brand"] == {"org_name": "Example Org"}
    assert saved["allowed_admins"] == ["admin"]
    assert saved["failure_alert_url"] == "https://hooks.example.com/alert"
    assert saved["jawa_address"] == "https://jawa.example.com"
    assert saved["jps_url"] == "https://jamf.example.com"
    assert saved["session_timeout_minutes"] == 15


def test_first_setup_save_keeps_posted_admins_and_alert(
    logged_in_client, jawa_env
):
    jawa_env.server_file.unlink()

    logged_in_client.post(
        "/setup",
        data={
            **FORM,
            "allowed_admins": "pytest-admin",
            "failure_alert_url": "https://hooks.example.com/alert",
        },
    )

    saved = json.loads(jawa_env.server_file.read_text())
    assert saved["allowed_admins"] == ["pytest-admin"]
    assert saved["failure_alert_url"] == "https://hooks.example.com/alert"
    assert saved["jawa_address"] == "https://jawa.example.com"
