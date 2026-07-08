"""Template enable/import → the resulting webhook actually fires (B1)."""

import io
import json
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
    logged_in_client, jawa_env
):
    resp = logged_in_client.post(
        "/templates/device-naming/enable",
        data={"webhook_name": "dn-hook"},
    )
    assert resp.status_code in (200, 302)
    entry = data_store.get_webhook_by_name("dn-hook")
    assert entry is not None
    # Canonical shape: all three auth keys present, defaulting to "null".
    assert entry["webhook_username"] == "null"
    assert entry["webhook_password"] == "null"
    assert entry["api_key"] == "null"


def test_enabled_template_webhook_fires(
    logged_in_client, jawa_env, fake_popen
):
    logged_in_client.post(
        "/templates/device-naming/enable",
        data={"webhook_name": "dn-hook"},
    )
    resp = logged_in_client.post(
        "/hooks/dn-hook",
        json={"webhook": {"webhookEvent": "ComputerCheckIn"}},
    )
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1


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
