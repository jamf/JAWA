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


class ConfigurablePopen:
    """A Popen stub whose failure dimensions are actually variable.

    RecordingPopen hard-codes ASCII stdout and `wait() -> 0`, so the two
    dimensions the receiver narrows -- the decode and the exit code --
    could not fail in the suite. Inverting `if return_code != 0:` in
    jawa_receiver used to leave all 419 tests passing.
    """

    def __init__(self, stdout=b"", returncode=0, raises=None):
        self._stdout = stdout
        self._returncode = returncode
        self._raises = raises

    def __call__(self, args, stdout=None, stderr=None):
        if self._raises is not None:
            raise self._raises
        self.stdout = io.BytesIO(self._stdout)
        return self

    def wait(self):
        return self._returncode


def _post_hook(client, jawa_env, monkeypatch, popen, **overrides):
    _make_webhook(jawa_env, **overrides)
    monkeypatch.setattr(subprocess, "Popen", popen)
    return client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )


@pytest.mark.parametrize(
    "stdout",
    [
        pytest.param("Renamed café-MacBook\n".encode(), id="utf8-accent"),
        pytest.param("記録しました\n".encode(), id="utf8-cjk"),
        pytest.param(b"latin-1 caf\xe9\n", id="invalid-utf8"),
    ],
)
def test_non_ascii_script_output_does_not_fail_the_request(
    client, jawa_env, monkeypatch, stdout
):
    """A device name with an accent is not an error.

    The response path decoded ascii while the log path decoded utf-8, so
    a script that exited 0 and printed a non-ASCII device name raised
    UnicodeDecodeError -> HTTP 500. Jamf Pro then recorded a failed
    delivery for work that had already succeeded, and retried it.
    Jamf device names are user-assigned and routinely non-ASCII.
    """
    resp = _post_hook(
        client,
        jawa_env,
        monkeypatch,
        ConfigurablePopen(stdout=stdout, returncode=0),
        output=True,
    )
    assert resp.status_code == 202, (
        f"successful script with non-ASCII stdout returned "
        f"{resp.status_code}"
    )


def test_non_zero_exit_is_not_reported_as_success(
    client, jawa_env, monkeypatch
):
    """A script that ran and failed must not answer 2xx.

    This is the assertion whose absence let `if return_code != 0:` be
    inverted with the whole suite still green.
    """
    resp = _post_hook(
        client,
        jawa_env,
        monkeypatch,
        ConfigurablePopen(stdout=b"boom\n", returncode=1),
    )
    assert resp.status_code >= 500, (
        f"script exited 1 but the receiver answered {resp.status_code}; "
        f"Jamf Pro would record a successful delivery"
    )


@pytest.mark.parametrize(
    "err",
    [
        pytest.param(FileNotFoundError("no such script"), id="missing"),
        pytest.param(PermissionError("not executable"), id="not-executable"),
    ],
)
def test_script_that_cannot_start_is_not_reported_as_success(
    client, jawa_env, monkeypatch, err
):
    """A retired or chmod-stripped script must not answer 2xx.

    Deleting a webhook while Jamf Pro is unreachable retires the script
    but leaves the Jamf webhook enabled, so this is reachable without
    anyone hand-editing anything.
    """
    resp = _post_hook(
        client, jawa_env, monkeypatch, ConfigurablePopen(raises=err)
    )
    assert resp.status_code >= 500, (
        f"Popen raised {type(err).__name__} but the receiver answered "
        f"{resp.status_code}"
    )
    assert "valid webhook received" not in resp.get_data(as_text=True)


def test_disabled_template_webhook_is_refused(client, jawa_env, fake_popen):
    """`enabled: False` must mean the JAWA endpoint is not live.

    template_view stores enabled=False for triggers Jamf Pro creates in
    the disabled state, and the enable screen tells the operator the
    webhook "is not yet enabled". The receiver never read the field, so
    that notice was false and the endpoint was open from that moment.
    """
    _make_webhook(jawa_env, enabled=False)
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 401
    assert fake_popen.calls == [], "a disabled automation executed its script"


def test_absent_enabled_key_still_runs(client, jawa_env, fake_popen):
    """Only an explicit False rejects.

    The non-template handlers write no `enabled` key at all, so treating
    a missing key as disabled would break every Jamf Pro, Okta, custom
    and timed automation.
    """
    _make_webhook(jawa_env)
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 200
    assert len(fake_popen.calls) == 1
