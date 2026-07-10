"""The 'Setup Required' error must link the user to /setup.

Creating a jamfpro/okta automation before JAWA is configured raises
AutomationError("Setup Required", ...). The error page must give the
admin a direct, in-page way to reach /setup instead of dead-ending.
"""

import json


def _unconfigure_jawa(jawa_env):
    # Remove jawa_address so get_jawa_address() is falsy -> Setup Required.
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))


def test_jamfpro_new_without_jawa_links_to_setup(logged_in_client, jawa_env):
    _unconfigure_jawa(jawa_env)
    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data={"webhook_name": "test-hook"},
    )
    body = resp.data.decode()
    assert "Setup Required" in body
    # The page offers a direct link to /setup (the action the user needs).
    assert 'href="/setup"' in body
    # Friendly label, not the raw path as the only text.
    assert "Go to Setup" in body
    # Internal navigation -- not a new tab.
    assert 'href="/setup" target="_blank"' not in body


def test_okta_new_without_jawa_links_to_setup(logged_in_client, jawa_env):
    _unconfigure_jawa(jawa_env)
    # Okta's handler reads the name from "webhookname" (no underscore).
    resp = logged_in_client.post(
        "/automations/okta/new",
        data={"webhookname": "test-okta"},
    )
    body = resp.data.decode()
    assert "Setup Required" in body
    assert 'href="/setup"' in body
    assert "Go to Setup" in body
