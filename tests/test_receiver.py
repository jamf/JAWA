"""Inbound webhook receiver: auth validation and script execution.

Script execution is stubbed at subprocess.Popen, so these tests
verify the full request -> validate -> execute pipeline without
running real scripts.
"""

import base64
import io
import json
import subprocess

import pytest


class RecordingPopen:
    """Stands in for subprocess.Popen and records invocations."""

    calls = []

    def __init__(self, args, stdout=None, stderr=None):
        RecordingPopen.calls.append(args)
        self.stdout = io.BytesIO(b"script ran\n")

    def wait(self):
        return 0


@pytest.fixture()
def fake_popen(monkeypatch):
    RecordingPopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    return RecordingPopen


def _basic_auth(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _make_webhook(jawa_env, **overrides):
    entry = {
        "name": "testhook",
        "tag": "custom",
        "script": str(jawa_env.scripts_dir / "hook_script.sh"),
        "webhook_username": "hookuser",
        "webhook_password": "hookpass",
        "api_key": "null",
        "output": False,
        "description": "harness webhook",
    }
    entry.update(overrides)
    jawa_env.add_webhook(entry)
    return entry


PAYLOAD = {"webhook": {"webhookEvent": "ComputerCheckIn"}}


def test_valid_auth_runs_script(client, jawa_env, fake_popen):
    entry = _make_webhook(jawa_env)
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 200
    assert resp.get_json()["result"] == "valid webhook received"
    assert len(fake_popen.calls) == 1
    argv = fake_popen.calls[0]
    assert argv[0] == entry["script"]
    # The whole payload is passed as a single JSON argument.
    assert json.loads(argv[1]) == PAYLOAD


def test_wrong_password_is_rejected(client, jawa_env, fake_popen):
    _make_webhook(jawa_env)
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "wrong"),
    )
    assert resp.status_code == 401
    assert fake_popen.calls == []


def test_unknown_webhook_is_rejected(client, jawa_env, fake_popen):
    resp = client.post(
        "/hooks/ghosthook",
        json=PAYLOAD,
        headers=_basic_auth("any", "any"),
    )
    assert resp.status_code == 401
    assert fake_popen.calls == []


def test_401_body_does_not_reflect_the_webhook_name(
    client, jawa_env, fake_popen
):
    """A bare-string return is served as text/html, so the caller-supplied
    webhook name must never reach the 401 body raw -- that was a reflected
    XSS on JAWA's own origin. The payload carries no slash because the
    route's default converter matches a single path segment.
    """
    marker = "<img src=x onerror=alert(1)>"
    resp = client.post(
        f"/hooks/{marker}",
        json=PAYLOAD,
        headers=_basic_auth("any", "any"),
    )
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert marker not in body
    assert "onerror" not in body
    assert "<img" not in body
    assert fake_popen.calls == []


def test_api_key_auth_runs_script(client, jawa_env, fake_popen):
    _make_webhook(
        jawa_env,
        webhook_username="null",
        webhook_password="null",
        api_key="sekrit",
    )
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers={"x-api-key": "sekrit"},
    )
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1


def test_noauth_webhook_accepts_anonymous_post(
    client, jawa_env, fake_popen
):
    # Documented posture (ASSESSMENT.md): a webhook stored with the
    # "null" sentinels is open to anyone who knows its name. If this
    # test starts failing, the auth model changed on purpose --
    # update the assessment.
    _make_webhook(
        jawa_env,
        webhook_username="null",
        webhook_password="null",
        api_key="null",
    )
    resp = client.post("/hooks/testhook", json=PAYLOAD)
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1


def test_custom_output_returns_script_result(
    client, jawa_env, fake_popen
):
    _make_webhook(jawa_env, output=True)
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 202
    assert "script ran" in resp.get_json()["result"]


def test_okta_verification_challenge_is_echoed(client, jawa_env):
    resp = client.post(
        "/hooks/anyhook",
        headers={"x-okta-verification-challenge": "abc123"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"verification": "abc123"}


def test_legacy_entry_missing_auth_keys_self_heals(
    client, jawa_env, fake_popen
):
    # A pre-fix template webhook: no auth keys at all. The tolerant
    # receiver must treat missing keys as "null" (open) and fire,
    # rather than returning a permanent 401 (bug B1).
    _make_webhook(jawa_env)
    # Strip the auth keys to simulate a legacy template entry.
    data = json.loads(jawa_env.webhooks_file.read_text())
    for key in ("webhook_username", "webhook_password", "api_key"):
        data[0].pop(key, None)
    jawa_env.webhooks_file.write_text(json.dumps(data))

    resp = client.post("/hooks/testhook", json=PAYLOAD)
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1


def test_null_json_body_is_a_teapot(client, jawa_env, fake_popen):
    resp = client.post(
        "/hooks/testhook",
        data="null",
        content_type="application/json",
    )
    assert resp.status_code == 418
    assert fake_popen.calls == []


def test_bodyless_post_returns_4xx(client, jawa_env, fake_popen):
    resp = client.post("/hooks/testhook")
    assert 400 <= resp.status_code < 500
    assert fake_popen.calls == []


def test_get_method_returns_405(client, jawa_env, fake_popen):
    resp = client.get("/hooks/testhook")
    assert resp.status_code == 405
    assert fake_popen.calls == []
