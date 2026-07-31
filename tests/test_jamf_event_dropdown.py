"""The Jamf event dropdown is generated from the shared catalog.

One source of truth for the event list: the reference pages and this
form read the same file, so they cannot drift. The rendered values are
the exact Jamf event strings -- they are stored on the webhook and
matched against the inbound payload's webhookEvent.
"""

import json
import re

import pytest

from bin.data_store import get_webhook_schemas


def _catalog_events():
    return [
        event
        for events in get_webhook_schemas()["categories"].values()
        for event in events
    ]


def _event_select_tag(body):
    """The <select name="event"> opening tag on its own.

    Other fields on the form carry `required` too, so an attribute
    assertion has to be scoped to this tag or it cannot discriminate.
    """
    match = re.search(r'<select[^>]*name="event"[^>]*>', body)
    assert match, "the event select is missing entirely"
    return match.group(0)


def _option_values(body):
    """Every non-empty option value in document order.

    The placeholder renders as value="" and is excluded, so this is the
    catalog options plus a "Stored event" option when one is rendered.
    """
    return re.findall(r'<option value="([^"]+)"', body)


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
    # An option per catalog event and no more. No stored event exists on
    # the create form, so the only other option is the value=""
    # placeholder, which _option_values excludes. A count read off the
    # page, not a literal that has to be bumped when Jamf adds an event.
    assert _option_values(body) == events
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
    # The placeholder is only a placeholder if the browser refuses the
    # submission: a webhook saved with no event never matches an inbound
    # webhookEvent, so it exists and never fires.
    assert "required" in _event_select_tag(body)


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
    # "Keep current" only works if the empty option is submittable, so
    # the attribute the create form carries must be absent here.
    assert "required" not in _event_select_tag(body)


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
