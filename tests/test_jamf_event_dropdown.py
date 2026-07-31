"""The Jamf event dropdown is generated from the shared catalog.

One source of truth for the event list: the reference pages and this
form read the same file, so they cannot drift. The rendered values are
the exact Jamf event strings -- they are stored on the webhook and
matched against the inbound payload's webhookEvent.
"""

import json

import pytest

from bin.data_store import get_webhook_schemas


def _catalog_events():
    return [
        event
        for events in get_webhook_schemas()["categories"].values()
        for event in events
    ]


def test_create_form_groups_events_by_category(logged_in_client, jawa_env):
    body = logged_in_client.get(
        "/automations/jamfpro/new"
    ).data.decode()
    for category in get_webhook_schemas()["categories"]:
        assert f'<optgroup label="{category}">' in body


def test_create_form_lists_every_catalog_event(logged_in_client, jawa_env):
    body = logged_in_client.get(
        "/automations/jamfpro/new"
    ).data.decode()
    events = _catalog_events()
    assert len(events) == 23
    for event in events:
        assert f'value="{event}"' in body


def test_create_form_keeps_the_required_empty_placeholder(
    logged_in_client, jawa_env
):
    body = logged_in_client.get(
        "/automations/jamfpro/new"
    ).data.decode()
    assert '<option value=""></option>' in body
    assert "-- Keep current --" not in body
    assert 'name="event"' in body
    assert "showSmartGroupNote(this.value)" in body


def _stored_webhook(event):
    return {
        "name": "dropdown-hook",
        "tag": "jamfpro",
        "event": event,
        "description": "dropdown test",
        "script": "/tmp/dropdown-hook.py",
        "jamf_id": "42",
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }


def test_edit_form_preselects_the_stored_event(
    logged_in_client, jawa_env
):
    jawa_env.add_webhook(_stored_webhook("ComputerCheckIn"))
    body = logged_in_client.get(
        "/automations/jamfpro/dropdown-hook/edit"
    ).data.decode()
    assert '<option value="ComputerCheckIn" selected>' in body
    assert "-- Keep current --" in body


def test_edit_form_preserves_an_event_missing_from_the_catalog(
    logged_in_client, jawa_env
):
    # A webhook stored before the MobileDeviceUnEnrolled recasing must
    # not be silently rewritten by opening and saving the edit form.
    jawa_env.add_webhook(_stored_webhook("MobileDeviceUnenrolled"))
    body = logged_in_client.get(
        "/automations/jamfpro/dropdown-hook/edit"
    ).data.decode()
    assert '<optgroup label="Stored event">' in body
    assert '<option value="MobileDeviceUnenrolled" selected>' in body


def test_dropdown_has_no_raw_hex_inline_style(logged_in_client, jawa_env):
    body = logged_in_client.get(
        "/automations/jamfpro/new"
    ).data.decode()
    assert 'style="color:#3c6aa7;"' not in body


def test_empty_catalog_leaves_the_form_renderable(
    logged_in_client, jawa_env
):
    # A damaged catalog must degrade, not 500 the creation form.
    jawa_env.webhook_schemas_file.write_text("{}")
    resp = logged_in_client.get("/automations/jamfpro/new")
    assert resp.status_code == 200
    assert 'name="event"' in resp.data.decode()


@pytest.mark.parametrize(
    "bad_value",
    [
        "JSSStartup",  # string
        {"JSSStartup": "x"},  # mapping
    ],
    ids=["string", "mapping"],
)
def test_a_miscategorised_event_list_degrades_that_group_only(
    logged_in_client, jawa_env, bad_value
):
    # A hand edit that leaves one category holding a bare string or
    # mapping object instead of a list must drop that group, not the
    # whole form. Both damage shapes blow up the flatten with TypeError.
    jawa_env.webhook_schemas_file.write_text(
        json.dumps(
            {
                "categories": {
                    "Computer Events": ["ComputerAdded"],
                    "System Events": bad_value,
                },
                "schemas": {},
                "examples": {},
            }
        )
    )
    resp = logged_in_client.get("/automations/jamfpro/new")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert '<optgroup label="Computer Events">' in body
    assert 'value="ComputerAdded"' in body
    assert '<optgroup label="System Events">' not in body
