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
    assert entry["webhook_username"] == "null"
    assert entry["webhook_password"] == "null"
    assert entry["api_key"] == "null"


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
    try:
        logged_in_client.post(
            "/templates/teams-notification/enable", data=form
        )
    except Exception:
        # Task 5 adds the try/except that renders the error page; until
        # then the AutomationError propagates. Either way nothing must
        # be written.
        pass
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


def test_template_view_has_no_direct_webhook_io():
    import inspect
    from views import template_view

    src = inspect.getsource(template_view)
    assert "_register_webhook" not in src
    assert "_load_webhooks" not in src
    # No direct open() of the webhooks file remains.
    assert "open(WEBHOOKS_FILE" not in src
