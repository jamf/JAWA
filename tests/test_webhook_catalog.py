"""The Jamf webhook event catalog is static reference data.

It feeds two surfaces — the /reference/webhooks pages and the Jamf
creation form's event dropdown — so its internal consistency is a
correctness concern: an event value that drifts from Jamf Pro's real
string is stored on the webhook and then never matches the inbound
payload's webhookEvent.
"""

import json

from bin.data_store import get_webhook_schemas

# Jamf Pro's authoritative event set (maintainer-confirmed against the
# Jamf Pro webhook creation UI, 2026-07-24).
JAMF_EVENTS = {
    "ComputerAdded",
    "ComputerCheckIn",
    "ComputerInventoryCompleted",
    "ComputerPatchPolicyCompleted",
    "ComputerPolicyFinished",
    "ComputerPushCapabilityChanged",
    "DeviceAddedToDEP",
    "DeviceRateLimited",
    "JSSShutdown",
    "JSSStartup",
    "MobileDeviceCheckIn",
    "MobileDeviceCommandCompleted",
    "MobileDeviceEnrolled",
    "MobileDeviceInventoryCompleted",
    "MobileDevicePushSent",
    "MobileDeviceUnEnrolled",
    "PatchSoftwareTitleUpdated",
    "PushSent",
    "RestAPIOperation",
    "SCEPChallenge",
    "SmartGroupComputerMembershipChange",
    "SmartGroupMobileDeviceMembershipChange",
    "SmartGroupUserMembershipChange",
}


def _flatten(categories):
    return [e for events in categories.values() for e in events]


def test_catalog_covers_exactly_the_jamf_event_set(jawa_env):
    catalog = get_webhook_schemas()
    assert set(_flatten(catalog["categories"])) == JAMF_EVENTS


def test_catalog_lists_each_event_once(jawa_env):
    flat = _flatten(get_webhook_schemas()["categories"])
    assert len(flat) == len(set(flat)) == 23


def test_every_categorized_event_has_a_schema(jawa_env):
    catalog = get_webhook_schemas()
    for event in _flatten(catalog["categories"]):
        entry = catalog["schemas"].get(event)
        assert entry, f"{event} is categorized but has no schema entry"
        assert entry["description"]


def test_every_example_matches_a_schema_and_its_own_key(jawa_env):
    catalog = get_webhook_schemas()
    for event, example in catalog["examples"].items():
        assert event in catalog["schemas"]
        # The stored webhookEvent must equal the key, or the reference
        # page would show a payload labelled as a different event.
        assert example["webhook"]["webhookEvent"] == event


def test_mobile_device_unenrolled_uses_jamfs_capital_e(jawa_env):
    catalog = get_webhook_schemas()
    assert "MobileDeviceUnEnrolled" in catalog["schemas"]
    assert "MobileDeviceUnEnrolled" in catalog["examples"]
    # The lowercase-e spelling never matches Jamf's payload.
    assert "MobileDeviceUnenrolled" not in catalog["schemas"]
    assert "MobileDeviceUnenrolled" not in catalog["examples"]
    assert "MobileDeviceUnenrolled" not in _flatten(catalog["categories"])


def test_device_rate_limited_is_present_and_marked_pending(jawa_env):
    catalog = get_webhook_schemas()
    entry = catalog["schemas"]["DeviceRateLimited"]
    # Field schema + payload are unconfirmed; the page must say so
    # rather than show invented fields.
    assert entry["pending"] is True
    assert entry["schema"] == {}
    assert "DeviceRateLimited" not in catalog["examples"]


def test_events_without_a_pending_marker_have_fields_and_a_payload(jawa_env):
    catalog = get_webhook_schemas()
    for event, entry in catalog["schemas"].items():
        if entry.get("pending"):
            continue
        assert entry["schema"], f"{event} has an empty field schema"
        assert event in catalog["examples"], f"{event} has no example"


def test_missing_catalog_degrades_to_empty_structures(jawa_env):
    jawa_env.webhook_schemas_file.unlink()
    catalog = get_webhook_schemas()
    # Never raise: a broken catalog must not 500 the creation form.
    assert catalog == {"categories": {}, "schemas": {}, "examples": {}}


def test_undecodable_catalog_degrades_to_empty_structures(jawa_env):
    # A hand edit saved in a non-UTF-8 encoding: 0x92 is a Latin-1
    # curly apostrophe, which is not valid UTF-8. The resulting
    # UnicodeDecodeError is a ValueError, not an OSError, so it has to
    # be caught explicitly or it escapes the fail-soft guard.
    jawa_env.webhook_schemas_file.write_bytes(
        b'{"categories": {}, "schemas": {"X": {"description":'
        b' "Jamf\x92s device"}}, "examples": {}}'
    )
    catalog = get_webhook_schemas()
    assert catalog == {"categories": {}, "schemas": {}, "examples": {}}


def test_wrong_typed_sections_degrade_to_empty_structures(jawa_env):
    # A hand edit turns an object into an array. The top-level object
    # check still passes, so without a per-section type check the list
    # reaches the caller and .items() raises inside the template.
    jawa_env.webhook_schemas_file.write_text(
        json.dumps(
            {
                "categories": ["Computer Events"],
                "schemas": "not a dict",
                "examples": 17,
            }
        )
    )
    catalog = get_webhook_schemas()
    assert catalog == {"categories": {}, "schemas": {}, "examples": {}}
    # Callers iterate these as mappings; every value must be one.
    for section in catalog.values():
        assert section.items() is not None
