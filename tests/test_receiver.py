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

from bin import failure_alert

JAMF_URL = "https://jamf.example.test"


class RecordingPopen:
    """Stands in for subprocess.Popen and records invocations."""

    calls = []

    def __init__(self, args, stdout=None, stderr=None, **kwargs):
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


def test_noauth_webhook_accepts_anonymous_post(client, jawa_env, fake_popen):
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


def test_custom_output_returns_script_result(client, jawa_env, fake_popen):
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

    def __call__(self, args, stdout=None, stderr=None, **kwargs):
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
        f"successful script with non-ASCII stdout returned {resp.status_code}"
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


def test_runs_are_recorded_and_shown(logged_in_client, jawa_env, monkeypatch):
    client = logged_in = logged_in_client
    _make_webhook(jawa_env)
    headers = _basic_auth("hookuser", "hookpass")
    monkeypatch.setattr(
        subprocess, "Popen", ConfigurablePopen(stdout=b"all good\n")
    )
    assert client.post("/hooks/testhook", json=PAYLOAD, headers=headers)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        ConfigurablePopen(stdout=b"it broke\n", returncode=1),
    )
    failed = client.post("/hooks/testhook", json=PAYLOAD, headers=headers)
    assert failed.status_code == 500

    runs = json.loads(jawa_env.runs_file.read_text())["testhook"]
    assert [r["exit_code"] for r in runs] == [1, 0]

    body = logged_in.get("/automations/custom/testhook").data.decode()
    assert "Succeeded" in body
    assert "Failed" in body
    assert "it broke" in body
    assert "Last run failed" in logged_in.get("/dashboard").data.decode()


def test_run_output_masks_secrets_on_detail_page(
    logged_in_client, jawa_env, monkeypatch
):
    _make_webhook(jawa_env)
    headers = _basic_auth("hookuser", "hookpass")
    monkeypatch.setattr(
        subprocess,
        "Popen",
        ConfigurablePopen(stdout=b'api_token="abc123"\ndone\n'),
    )
    logged_in_client.post("/hooks/testhook", json=PAYLOAD, headers=headers)

    body = logged_in_client.get("/automations/custom/testhook").data.decode()
    assert "abc123" not in body
    assert "********" in body
    assert "done" in body


def test_run_history_keeps_twenty_per_automation(
    client, jawa_env, monkeypatch
):
    _make_webhook(jawa_env)
    headers = _basic_auth("hookuser", "hookpass")
    monkeypatch.setattr(subprocess, "Popen", ConfigurablePopen())
    for _ in range(25):
        client.post("/hooks/testhook", json=PAYLOAD, headers=headers)
    runs = json.loads(jawa_env.runs_file.read_text())
    assert len(runs["testhook"]) == 20


# --- Okta secret ---


def _okta_entry(jawa_env, secret="s3cret-okta-value"):
    entry = {
        "name": "oktahook",
        "tag": "okta",
        "script": str(jawa_env.scripts_dir / "hook_script.sh"),
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
        "okta_event": "user.lifecycle.deactivate",
    }
    if secret:
        entry["okta_secret"] = secret
    jawa_env.add_webhook(entry)


def test_okta_hook_requires_its_secret(client, jawa_env, fake_popen):
    _okta_entry(jawa_env)
    resp = client.post("/hooks/oktahook", json=PAYLOAD)
    assert resp.status_code == 401
    wrong = client.post(
        "/hooks/oktahook", json=PAYLOAD, headers={"Authorization": "nope"}
    )
    assert wrong.status_code == 401
    assert fake_popen.calls == []

    ok = client.post(
        "/hooks/oktahook",
        json=PAYLOAD,
        headers={"Authorization": "s3cret-okta-value"},
    )
    assert ok.status_code == 200
    assert len(fake_popen.calls) == 1


def test_okta_entry_without_a_secret_fails_closed(
    client, jawa_env, fake_popen
):
    _okta_entry(jawa_env, secret=None)
    resp = client.post("/hooks/oktahook", json=PAYLOAD)
    assert resp.status_code == 401
    literal = client.post(
        "/hooks/oktahook",
        json=PAYLOAD,
        headers={"Authorization": "${api_key}"},
    )
    assert literal.status_code == 401
    assert fake_popen.calls == []


def test_okta_detail_page_tells_admin_to_recreate_old_entry(
    logged_in_client, jawa_env
):
    _okta_entry(jawa_env, secret=None)
    body = logged_in_client.get("/automations/okta/oktahook").get_data(
        as_text=True
    )
    assert "Delete it and create it again" in body


# --- Script timeout ---


def _pid_alive(pid):
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_hanging_script_is_killed_and_request_returns_504(
    client, jawa_env, monkeypatch, tmp_path
):
    import time

    monkeypatch.setenv("JAWA_SCRIPT_TIMEOUT", "1")
    pidfile = tmp_path / "pids"
    script = jawa_env.scripts_dir / "hook_script.sh"
    # The child sleeps in the background so that only a group kill stops it.
    script.write_text(
        f"#!/bin/sh\nsleep 60 &\necho $! > {pidfile}\necho $$ >> {pidfile}\nwait\n"
    )
    script.chmod(0o755)
    _make_webhook(jawa_env)

    began = time.monotonic()
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    elapsed = time.monotonic() - began

    assert resp.status_code == 504
    assert elapsed < 20
    pids = [int(p) for p in pidfile.read_text().split()]
    time.sleep(0.3)
    assert not any(_pid_alive(p) for p in pids)


def test_script_timeout_defaults_to_two_minutes(monkeypatch):
    from webhook import jawa_receiver

    monkeypatch.delenv("JAWA_SCRIPT_TIMEOUT", raising=False)
    assert jawa_receiver.script_timeout() == 120
    monkeypatch.setenv("JAWA_SCRIPT_TIMEOUT", "7")
    assert jawa_receiver.script_timeout() == 7
    monkeypatch.setenv("JAWA_SCRIPT_TIMEOUT", "garbage")
    assert jawa_receiver.script_timeout() == 120


# --- Failure alerts -------------------------------------------------------

ALERT_URL = "https://hooks.example.test/services/T000/B000/SECRET"


class RecordingPost:
    """Stands in for requests.post and records every alert it is asked to send."""

    def __init__(self, raises=None):
        self.calls = []
        self._raises = raises

    def __call__(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._raises is not None:
            raise self._raises

        class _Resp:
            status_code = 200

        return _Resp()


@pytest.fixture()
def alert_post(jawa_env, monkeypatch):
    """Set an alert URL, run alert threads inline, and record POSTs.

    The alert thread is started through jawa_receiver._start_alert_thread,
    so swapping it for a direct call makes the POST happen before the
    request returns. Rate-limit state is cleared per test.
    """
    from webhook import jawa_receiver

    jawa_receiver._last_alert_at.clear()
    server = json.loads(jawa_env.server_file.read_text())
    server["failure_alert_url"] = ALERT_URL
    jawa_env.server_file.write_text(json.dumps(server))

    def _inline(target, args):
        target(*args)

    recorder = RecordingPost()
    monkeypatch.setattr(jawa_receiver, "_start_alert_thread", _inline)
    monkeypatch.setattr(failure_alert.requests, "post", recorder)
    yield recorder
    jawa_receiver._last_alert_at.clear()


def test_failed_run_posts_one_alert(client, jawa_env, monkeypatch, alert_post):
    _make_webhook(jawa_env)
    monkeypatch.setattr(
        subprocess, "Popen", ConfigurablePopen(stdout=b"boom\n", returncode=3)
    )
    headers = _basic_auth("hookuser", "hookpass")
    first = client.post("/hooks/testhook", json=PAYLOAD, headers=headers)
    second = client.post("/hooks/testhook", json=PAYLOAD, headers=headers)

    # The response is the same as before alerts existed.
    assert first.status_code == 500
    assert second.status_code == 500
    assert len(alert_post.calls) == 1, alert_post.calls
    call = alert_post.calls[0]
    assert call["url"] == ALERT_URL
    assert call["timeout"] == 10
    assert "testhook" in call["json"]["text"]
    assert "(exit 3)" in call["json"]["text"]


def test_failed_run_without_alert_url_posts_nothing(
    client, jawa_env, monkeypatch
):
    from webhook import jawa_receiver

    jawa_receiver._last_alert_at.clear()
    recorder = RecordingPost()
    monkeypatch.setattr(failure_alert.requests, "post", recorder)
    _make_webhook(jawa_env)
    monkeypatch.setattr(
        subprocess, "Popen", ConfigurablePopen(stdout=b"boom\n", returncode=1)
    )
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 500
    assert recorder.calls == []


def test_alert_failure_does_not_change_the_response(
    client, jawa_env, monkeypatch, alert_post
):
    alert_post._raises = ConnectionError("hooks.example.test refused")
    _make_webhook(jawa_env)
    monkeypatch.setattr(
        subprocess, "Popen", ConfigurablePopen(stdout=b"boom\n", returncode=1)
    )
    resp = client.post(
        "/hooks/testhook",
        json=PAYLOAD,
        headers=_basic_auth("hookuser", "hookpass"),
    )
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "script exited 1"
    assert len(alert_post.calls) == 1


def test_setup_saves_and_renders_failure_alert_url(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/setup",
        data={
            "address": "https://jawa.example.test",
            "jss-lock": JAMF_URL,
            "failure_alert_url": f"  {ALERT_URL}  ",
            "session_timeout_minutes": "15",
        },
    )
    assert resp.status_code == 302
    saved = json.loads(jawa_env.server_file.read_text())
    assert saved["failure_alert_url"] == ALERT_URL

    page = logged_in_client.get("/setup").get_data(as_text=True)
    assert f'value="{ALERT_URL}"' in page

    # An empty field clears it.
    logged_in_client.post(
        "/setup",
        data={
            "address": "https://jawa.example.test",
            "jss-lock": JAMF_URL,
            "failure_alert_url": "",
        },
    )
    assert (
        json.loads(jawa_env.server_file.read_text())["failure_alert_url"] == ""
    )
