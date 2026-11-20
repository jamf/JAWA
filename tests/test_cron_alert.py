"""A failing timed automation posts the same chat alert as a webhook run."""

import json
import re

import pytest
import requests

from bin import failure_alert
from bin import run_cron

ALERT_URL = "https://hooks.example.test/services/T000/B000/SECRET"


class RecordingPost:
    """Stands in for requests.post and records every alert it is asked to send."""

    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def __call__(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.raises is not None:
            raise self.raises

        class _Resp:
            status_code = 200

        return _Resp()


def _add_cron(jawa_env, name, script):
    data = json.loads(jawa_env.cron_file.read_text())
    data.append(
        {
            "name": name,
            "description": "",
            "frequency": "Every day at 2:00 AM",
            "script": script,
        }
    )
    jawa_env.cron_file.write_text(json.dumps(data))


def _script(jawa_env, name, exit_code, executable=True):
    stub = jawa_env.scripts_dir / f"cron_{name}.sh"
    stub.write_text(f"#!/bin/sh\necho working\nexit {exit_code}\n")
    stub.chmod(0o700 if executable else 0o600)
    _add_cron(jawa_env, name, str(stub))
    return stub


def _set_alert_url(jawa_env, url=ALERT_URL):
    server = json.loads(jawa_env.server_file.read_text())
    server["failure_alert_url"] = url
    jawa_env.server_file.write_text(json.dumps(server))


@pytest.fixture()
def post(jawa_env, monkeypatch):
    recorder = RecordingPost()
    monkeypatch.setattr(failure_alert.requests, "post", recorder)
    return recorder


@pytest.fixture()
def alerting(jawa_env, post):
    _set_alert_url(jawa_env)
    return post


def _alerts_file(jawa_env):
    return jawa_env.data_dir / "cron_alerts.json"


def test_failing_script_posts_one_alert(jawa_env, alerting):
    _script(jawa_env, "NightlyExport", 3)

    assert run_cron.run("NightlyExport") == 3

    assert len(alerting.calls) == 1, alerting.calls
    call = alerting.calls[0]
    assert call["url"] == ALERT_URL
    assert call["timeout"] == 10
    assert re.fullmatch(
        r"JAWA: NightlyExport failed \(exit 3\) at "
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d",
        call["json"]["text"],
    ), call["json"]["text"]


def test_success_posts_nothing(jawa_env, alerting):
    _script(jawa_env, "NightlyExport", 0)

    assert run_cron.run("NightlyExport") == 0
    assert alerting.calls == []
    assert not _alerts_file(jawa_env).exists()


def test_no_alert_url_posts_nothing(jawa_env, post):
    _script(jawa_env, "NightlyExport", 3)

    assert run_cron.run("NightlyExport") == 3
    assert post.calls == []


def test_second_failure_inside_interval_posts_nothing(jawa_env, alerting):
    _script(jawa_env, "NightlyExport", 3)

    assert run_cron.run("NightlyExport") == 3
    assert run_cron.run("NightlyExport") == 3

    assert len(alerting.calls) == 1, alerting.calls
    saved = json.loads(_alerts_file(jawa_env).read_text())
    assert set(saved) == {"NightlyExport"}


def test_rate_limit_is_per_automation(jawa_env, alerting):
    _script(jawa_env, "First", 3)
    _script(jawa_env, "Second", 4)

    run_cron.run("First")
    run_cron.run("Second")

    assert [c["json"]["text"].split(" failed")[0] for c in alerting.calls] == [
        "JAWA: First",
        "JAWA: Second",
    ]


def test_failure_after_interval_posts_again(jawa_env, alerting, monkeypatch):
    _script(jawa_env, "NightlyExport", 3)
    clock = [1_000_000.0]
    monkeypatch.setattr(failure_alert.time, "time", lambda: clock[0])

    run_cron.run("NightlyExport")
    clock[0] += failure_alert.ALERT_INTERVAL_SECONDS - 1
    run_cron.run("NightlyExport")
    assert len(alerting.calls) == 1

    clock[0] += 2
    run_cron.run("NightlyExport")
    assert len(alerting.calls) == 2


@pytest.mark.parametrize(
    "content", ["{not json", "[1, 2]", '{"NightlyExport": "soon"}', ""]
)
def test_corrupt_rate_limit_file_is_treated_as_empty(
    jawa_env, alerting, content
):
    _script(jawa_env, "NightlyExport", 3)
    _alerts_file(jawa_env).write_text(content)

    assert run_cron.run("NightlyExport") == 3

    assert len(alerting.calls) == 1
    saved = json.loads(_alerts_file(jawa_env).read_text())
    assert isinstance(saved["NightlyExport"], float)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError("hooks.example.test refused"),
        requests.exceptions.Timeout("read timed out"),
        RuntimeError("anything else"),
    ],
)
def test_post_error_keeps_exit_code_and_does_not_raise(
    jawa_env, alerting, error
):
    alerting.raises = error
    _script(jawa_env, "NightlyExport", 5)

    assert run_cron.main(["NightlyExport"]) == 5
    assert len(alerting.calls) == 1


def test_script_that_cannot_start_alerts_with_126(jawa_env, alerting):
    _script(jawa_env, "NotExecutable", 0, executable=False)

    assert run_cron.run("NotExecutable") == 126

    assert len(alerting.calls) == 1
    assert (
        "JAWA: NotExecutable failed (exit 126) at "
        in (alerting.calls[0]["json"]["text"])
    )


def test_unknown_automation_alerts(jawa_env, alerting):
    assert run_cron.run("Missing") == 1

    assert len(alerting.calls) == 1
    assert (
        "JAWA: Missing failed (exit 1) at "
        in (alerting.calls[0]["json"]["text"])
    )


def test_corrupt_cron_file_still_alerts(jawa_env, alerting):
    jawa_env.cron_file.write_text("{not json")
    assert run_cron.run("anything") == 1
    assert len(alerting.calls) == 1
    assert (
        "JAWA: anything failed (exit 1) at "
        in (alerting.calls[0]["json"]["text"])
    )
