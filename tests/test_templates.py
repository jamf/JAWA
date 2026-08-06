"""Template enable/import → the resulting webhook actually fires (B1)."""

import io
import json
import os
import subprocess

import pytest

from bin import data_store


class RecordingPopen:
    calls = []

    def __init__(self, args, stdout=None, stderr=None):
        RecordingPopen.calls.append(args)
        self.stdout = io.BytesIO(b"ok\n")

    def wait(self):
        return 0


@pytest.fixture()
def fake_popen(monkeypatch):
    RecordingPopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    return RecordingPopen


def test_enabled_template_writes_canonical_auth_shape(
    logged_in_client, jawa_env, enable_form
):
    resp = logged_in_client.post(
        "/templates/device-naming/enable",
        data=enable_form("device-naming", webhook_name="dn-hook"),
    )
    assert resp.status_code in (200, 302)
    entry = data_store.get_webhook_by_name("dn-hook")
    assert entry is not None
    # Canonical shape: all three auth keys present, defaulting to "null".
    # The form now offers Basic/header auth, so "open" is the
    # unauthenticated branch of an explicit choice rather than the only
    # thing enable could write: with no "choice" field submitted,
    # _extract_auth_fields returns "null" for all three.
    assert entry["webhook_username"] == "null"
    assert entry["webhook_password"] == "null"
    assert entry["api_key"] == "null"


# The auth fields are labelled optional, so picking a radio and leaving
# the boxes blank is an expected action -- and the form makes that branch
# reachable for the first time from the enable path.
BLANK_AUTH_SUBMISSIONS = [
    ({"choice": "basic", "basic_username": "", "basic_password": ""}),
    ({"choice": "basic", "basic_username": "", "basic_password": "pw"}),
    ({"choice": "custom", "api_key": ""}),
]


@pytest.mark.parametrize("auth_fields", BLANK_AUTH_SUBMISSIONS)
def test_blank_auth_field_does_not_lock_the_webhook_out(
    logged_in_client, jawa_env, enable_form, auth_fields
):
    """A submitted-but-empty auth input posts "", which the get()
    default never replaced. _build_auth_xml then told Jamf NONE while
    the stored value stayed "", and the receiver defaults an
    unauthenticated request to "null" -- so "null" != "" made
    validate_webhook reject EVERY inbound event, permanently, behind a
    success page that said "Enabled".
    """
    from webhook import jawa_receiver

    form = enable_form("device-naming", webhook_name="blank-auth-hook")
    form.update(auth_fields)
    logged_in_client.post("/templates/device-naming/enable", data=form)

    entry = data_store.get_webhook_by_name("blank-auth-hook")
    assert entry is not None
    # No stored auth credential may ever be the empty string: the
    # receiver's no-auth sentinel is the string "null".
    for key in ("webhook_username", "webhook_password", "api_key"):
        assert entry[key] != "", f"{key} stored as an empty string"

    # The assertion with the teeth: an unauthenticated inbound request
    # (the receiver's "null" x3 default) must still validate for any
    # field the user left blank.
    expected = {
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }
    for key, value in expected.items():
        if entry[key] != value:
            # A field the user actually filled in: auth is genuinely on,
            # so an unauthenticated request SHOULD be refused.
            break
    else:
        assert jawa_receiver.validate_webhook(
            "blank-auth-hook", "null", "null", "null"
        ), "an all-blank auth choice locked the webhook out"
        resp = logged_in_client.post(
            "/hooks/blank-auth-hook",
            json={"webhook": {"webhookEvent": "MobileDeviceEnrolled"}},
        )
        assert resp.status_code == 200, (
            f"inbound event rejected {resp.status_code}; the webhook is "
            f"permanently locked out"
        )


def test_enabled_template_webhook_fires(
    logged_in_client, jawa_env, fake_popen, enable_form
):
    logged_in_client.post(
        "/templates/device-naming/enable",
        data=enable_form("device-naming", webhook_name="dn-hook"),
    )
    resp = logged_in_client.post(
        "/hooks/dn-hook",
        json={"webhook": {"webhookEvent": "ComputerCheckIn"}},
    )
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1
    # The receiver runs the script via a direct Popen with no directory
    # prefix, so the stored "script" must be an absolute path that exists
    # on disk -- otherwise the script silently never runs (bug B1).
    argv = fake_popen.calls[0]
    assert os.path.isabs(argv[0])
    assert os.path.exists(argv[0])


def test_enable_deploys_a_script_with_every_token_filled(
    logged_in_client, jawa_env, enable_form
):
    """End-to-end through the route: the deployed copy on disk must hold
    the submitted values as real Python and carry no leftover token. The
    old engine matched on placeholder, not token, so every token stayed
    baked in and the script ran against literal "__JAWA_..." strings.
    """
    url = "https://logic.example.test/invoke?a=1&b=2&sig=Ab%2FCd"
    logged_in_client.post(
        "/templates/teams-notification/enable",
        data=enable_form(
            "teams-notification",
            webhook_name="teams-hook",
            TEAMS_WEBHOOK_URL=url,
        ),
    )
    entry = data_store.get_webhook_by_name("teams-hook")
    assert entry is not None
    with open(entry["script"], "r", encoding="utf-8") as handle:
        deployed = handle.read()
    assert "__JAWA_" not in deployed
    namespace = {}
    exec(compile(deployed, entry["script"], "exec"), namespace)
    assert namespace["TEAMS_WEBHOOK_URL"] == url


def test_enable_with_a_field_left_blank_deploys_nothing(
    logged_in_client, jawa_env, enable_form
):
    """Failing loud is the point: a half-filled form used to yield a
    registered webhook pointing at a script still holding tokens.
    """
    form = enable_form("teams-notification", webhook_name="blank-hook")
    form["TEAMS_WEBHOOK_URL"] = ""
    resp = logged_in_client.post(
        "/templates/teams-notification/enable", data=form
    )
    # The route now catches AutomationError and renders the error page.
    # Asserting that explicitly, rather than swallowing whatever comes
    # back: a 500 from an unrelated regression would otherwise satisfy
    # "nothing was written" and pass silently.
    assert resp.status_code == 302
    assert "/error" in resp.headers["Location"]
    assert data_store.get_webhook_by_name("blank-hook") is None
    assert not os.listdir(str(jawa_env.scripts_dir))


def _traversal_package():
    return {
        "name": "evil",
        "trigger": {"event": "ComputerCheckIn"},
        "script": {"filename": "../../evil.sh", "content": "#!/bin/sh\n"},
    }


def test_import_rejects_traversal_filename(logged_in_client, jawa_env):
    import io as _io

    payload = json.dumps(_traversal_package()).encode()
    resp = logged_in_client.post(
        "/templates/import",
        data={"package": (_io.BytesIO(payload), "evil.jawa.json")},
        content_type="multipart/form-data",
    )
    # Rejected via the existing error redirect; nothing written outside
    # SCRIPTS_DIR, and no webhook registered.
    assert resp.status_code in (302, 400)
    assert data_store.get_webhook_by_name("evil") is None
    import os

    scripts_dir = str(jawa_env.scripts_dir)
    traversal_target = os.path.normpath(
        os.path.join(scripts_dir, "..", "..", "evil.sh")
    )
    assert not os.path.exists(traversal_target)
    assert not os.path.exists(os.path.join(scripts_dir, "evil.sh"))


def _package(content, name="imported-hook"):
    return {
        "name": name,
        "description": "test package",
        "trigger": {"event": "ComputerCheckIn"},
        "script": {"filename": "imported.py", "content": content},
    }


def _upload(client, package):
    payload = json.dumps(package).encode()
    return client.post(
        "/templates/import",
        data={
            "package": (io.BytesIO(payload), "thing.jawa.json"),
        },
        content_type="multipart/form-data",
    )


def test_import_rejects_script_that_does_not_parse(
    logged_in_client, jawa_env
):
    """A truncated or malformed upload used to be written, chmod 0755'd
    and registered as a live webhook, then fail inside Popen where the
    only signal is a logged non-zero exit code (bug B16).
    """
    broken = "#!/usr/bin/env python3\ndef main():\n    x = json.loads(\n"
    resp = _upload(logged_in_client, _package(broken))

    assert resp.status_code in (200, 302)
    assert data_store.get_webhook_by_name("imported-hook") is None
    assert not os.path.isfile(
        os.path.join(str(jawa_env.scripts_dir), "imported.py")
    )


def test_import_accepts_script_using_a_runtime_global(
    logged_in_client, jawa_env
):
    """The gate is compile() only, deliberately not undefined-name
    analysis: a user's own script may legitimately rely on a runtime
    global, and rejecting that would be a regression. Bundled content
    is held to the stricter F821 bar in test_template_catalog.py.
    """
    uses_global = (
        "#!/usr/bin/env python3\n"
        "def main():\n"
        "    return some_runtime_helper()\n"
    )
    resp = _upload(logged_in_client, _package(uses_global))

    assert resp.status_code in (200, 302)
    assert data_store.get_webhook_by_name("imported-hook") is not None


def test_substitution_rejects_a_token_no_param_declares():
    """The survivor check must run even when the workflow declares no
    config_params. The early return for "nothing to substitute" used to
    skip it, so a template carrying a token with no catalog entry --
    exactly the drift the check exists to catch -- shipped with the
    placeholder baked into the deployed script.
    """
    from views._type_handlers.base import AutomationError
    from views.template_view import substitute_params

    with pytest.raises(AutomationError):
        substitute_params(
            'X = "__JAWA_ORPHAN__"\n', {"config_params": []}, {}, [], ""
        )


def test_enable_files_the_automation_under_jamfpro(
    logged_in_client, jawa_env
):
    """Templates wrote tag "custom" while carrying a Jamf event, so they
    were misfiled under Custom and edited against a form with no event
    field -- their trigger was invisible and uneditable (bug B14).
    """
    resp = logged_in_client.post(
        "/templates/device-naming/enable",
        data={
            "webhook_name": "Device-Naming-by-Asset-Tag",
            "server_url": "https://prod.jamfcloud.com",
            "client_id": "abc",
            "client_secret": "shh",
        },
    )
    assert resp.status_code in (200, 302)
    entry = data_store.get_webhook_by_name("Device-Naming-by-Asset-Tag")
    assert entry is not None
    assert entry["tag"] == "jamfpro"
    assert entry["event"] == "MobileDeviceEnrolled"
    assert entry["jamf_id"] == "77"


def test_enable_writes_nothing_when_jamf_rejects(
    logged_in_client, jawa_env, monkeypatch, jamf_fake_http
):
    """Jamf-side creation happens BEFORE the local write, so a 409 or a
    timeout leaves no orphaned script and no half-configured
    automation.
    """
    import requests as requests_module

    response_cls, default_post = jamf_fake_http

    def _conflict(url, **kwargs):
        if "/JSSResource/webhooks/id/0" in url:
            return response_cls({}, status_code=409, text="duplicate")
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests_module, "post", _conflict)

    logged_in_client.post(
        "/templates/device-naming/enable",
        data={
            "webhook_name": "Device-Naming-by-Asset-Tag",
            "server_url": "https://prod.jamfcloud.com",
            "client_id": "abc",
            "client_secret": "shh",
        },
    )

    assert (
        data_store.get_webhook_by_name("Device-Naming-by-Asset-Tag") is None
    )
    written = os.listdir(str(jawa_env.scripts_dir))
    assert written == [], f"orphaned script(s) left behind: {written}"


def test_smart_group_template_warns_it_is_not_live_yet(
    logged_in_client, jawa_env, enable_form
):
    """Jamf creates a smart-group webhook DISABLED (enablement "false"),
    so it does not fire until the admin picks a smart group in Jamf Pro.
    Three of the bundled templates use a smart-group event. Reporting a
    bare "Enabled template" for those leaves the user believing the
    automation is live -- the same "no indication the user must do more"
    failure B14 exists to close.
    """
    resp = logged_in_client.post(
        "/templates/smart-group-slack/enable",
        data=enable_form("smart-group-slack", webhook_name="sg-hook"),
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]

    body = logged_in_client.get("/success").get_data(as_text=True)
    assert "not yet enabled" in body, (
        "the success page does not warn that Jamf created the webhook "
        "disabled; the user thinks the automation is live"
    )
    assert "Smart Group" in body

    # And the stored record must agree with the remote object: Jamf
    # created this one with enablement "false", so a flat True here
    # would make any future "is it live?" read lie.
    entry = data_store.get_webhook_by_name("sg-hook")
    assert entry["enabled"] is False


def test_non_smart_group_template_is_stored_enabled(
    logged_in_client, jawa_env, enable_form
):
    """The other side of the same rule: a normal event is created
    enabled, so the flag must not be blanket-false either.
    """
    logged_in_client.post(
        "/templates/device-naming/enable",
        data=enable_form("device-naming", webhook_name="live-hook"),
    )
    entry = data_store.get_webhook_by_name("live-hook")
    assert entry["enabled"] is True


def test_enable_links_to_the_new_webhook_in_jamf(
    logged_in_client, jawa_env, enable_form
):
    """jamf_id is captured, so the success page can deep-link the object
    the way the create path does.
    """
    logged_in_client.post(
        "/templates/device-naming/enable",
        data=enable_form("device-naming", webhook_name="dn-link-hook"),
    )
    body = logged_in_client.get("/success").get_data(as_text=True)
    assert "/webhooks.html?id=77" in body


def test_enable_rejects_a_name_with_spaces(logged_in_client, jawa_env):
    """The name goes into the callback URL Jamf calls; Jamf rejects
    names containing a space.
    """
    logged_in_client.post(
        "/templates/device-naming/enable",
        data={
            "webhook_name": "Device Naming by Asset Tag",
            "server_url": "https://prod.jamfcloud.com",
            "client_id": "abc",
            "client_secret": "shh",
        },
    )
    assert data_store.get_webhook_by_name("Device Naming by Asset Tag") is None


def test_any_event_template_offers_a_real_event_to_pick(
    logged_in_client, jawa_env
):
    """teams-notification declares trigger_event null, so the server
    rejects the POST unless the form supplies an event. Without the
    picker the page is a dead end: every submit hits "Choose the Jamf
    Pro event to listen for." with no field to satisfy it.
    """
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "webhook_schemas.json",
        ),
        "r",
        encoding="utf-8",
    ) as handle:
        schemas = json.load(handle)

    body = logged_in_client.get(
        "/templates/teams-notification/enable"
    ).get_data(as_text=True)
    assert 'name="event"' in body, "the any-event template has no picker"
    # Real schema keys, not invented labels: the value is sent to Jamf.
    assert any(f'value="{event}"' in body for event in schemas["schemas"])


def test_fixed_event_template_does_not_offer_a_picker(
    logged_in_client, jawa_env
):
    """The other six templates hard-declare their trigger. Offering a
    picker there would let the admin choose an event the script cannot
    parse, and the server ignores the field anyway.
    """
    body = logged_in_client.get(
        "/templates/device-naming/enable"
    ).get_data(as_text=True)
    assert 'name="event"' not in body
    assert "MobileDeviceEnrolled" in body


def test_enable_form_prefills_a_name_jamf_will_accept(
    logged_in_client, jawa_env
):
    """The field used to default to the human title, which contains
    spaces -- so the prefilled value was one the server now rejects
    outright. It must come from the catalog's hook_name (Task 2).
    """
    import re

    catalog_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "workflows",
        "workflow_config.json",
    )
    with open(catalog_path, "r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    for workflow in catalog:
        body = logged_in_client.get(
            f"/templates/{workflow['slug']}/enable"
        ).get_data(as_text=True)
        match = re.search(
            r'name="webhook_name"[^>]*?value="([^"]*)"', body, re.S
        )
        assert match, f"{workflow['slug']}: no prefilled name field"
        value = match.group(1)
        assert value == workflow["hook_name"], (
            f"{workflow['slug']}: form prefills {value!r}, catalog says "
            f"{workflow['hook_name']!r}"
        )
        assert " " not in value


def test_a_rejected_config_never_reaches_jamf(
    logged_in_client, jawa_env, monkeypatch, jamf_fake_http, enable_form
):
    """Ordering is the whole point: substitution runs BEFORE the Jamf
    POST, so a config substitute_params refuses cannot leave an orphan
    webhook in the customer's Jamf Pro that JAWA has no record of and
    the admin has to find and delete by hand.
    """
    import requests as requests_module

    _, default_post = jamf_fake_http
    creations = []

    def _counting_post(url, **kwargs):
        if "/JSSResource/webhooks/id/0" in url:
            creations.append(url)
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests_module, "post", _counting_post)

    # COOLDOWN_HOURS is the one numeric token: it is written bare into
    # an expression position, so _numeric_literal refuses a non-number
    # instead of deploying a script that will not compile.
    form = enable_form("event-tracker-sqlite", webhook_name="reject-hook")
    form["COOLDOWN_HOURS"] = "twelve"
    resp = logged_in_client.post(
        "/templates/event-tracker-sqlite/enable", data=form
    )

    assert resp.status_code == 302
    assert "/error" in resp.headers["Location"]
    assert creations == [], (
        f"{len(creations)} webhook(s) created in Jamf Pro for a config "
        f"JAWA then refused -- each one is an orphan"
    )
    assert data_store.get_webhook_by_name("reject-hook") is None
    assert not os.listdir(str(jawa_env.scripts_dir))


def test_template_view_has_no_direct_webhook_io():
    import inspect
    from views import template_view

    src = inspect.getsource(template_view)
    assert "_register_webhook" not in src
    assert "_load_webhooks" not in src
    # No direct open() of the webhooks file remains.
    assert "open(WEBHOOKS_FILE" not in src
