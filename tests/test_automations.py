"""Automation create/edit/delete success flow: PRG + one-shot flash."""

import io
import json

import pytest
import requests
from datetime import datetime, timedelta, timezone


def _custom_create_data():
    # custom_handler.process_create requires a name + an uploaded script.
    return {
        "custom_name": "prg-test-hook",
        "description": "prg test",
        "new_file": (
            io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
            "hook.py",
        ),
    }


def test_create_redirects_to_success(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    # PRG: the POST must 302 to /success, not render 200 inline.
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_success_flash_is_one_shot(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    # First GET renders the flashed context; second GET has no flash left.
    first = logged_in_client.get("/success")
    assert first.status_code == 200
    assert b"Webhook created" in first.data
    second = logged_in_client.get("/success")
    # Flash popped: the create message must not persist on a re-load.
    assert b"Webhook created" not in second.data


def test_edit_redirects_to_success(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    logged_in_client.get("/success")  # drain the create flash
    resp = logged_in_client.post(
        "/automations/custom/prg-test-hook/edit",
        data={
            "custom_name": "prg-test-hook",
            "description": "edited",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_delete_redirects_to_success(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    logged_in_client.get("/success")
    resp = logged_in_client.post(
        "/automations/custom/prg-test-hook/delete",
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_smart_group_notice_survives_flash(
    logged_in_client, jawa_env, monkeypatch
):
    # A smart-group event makes jamf_handler return a smart_group_notice.
    # The Jamf create POST reads resp.text (for the <id> scrape + logging),
    # which the shared fake_jamf post stub doesn't provide — so give this
    # test a post fake that returns Jamf-shaped XML.
    class _XmlResponse:
        status_code = 201
        text = "<webhook><id>42</id></webhook>"

    monkeypatch.setattr(requests, "post", lambda *a, **k: _XmlResponse())

    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data={
            "webhook_name": "sg-membership-hook",
            "event": "SmartGroupComputerMembershipChange",
            "description": "smart group prg test",
            "choice": "none",
            "new_file": (
                io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
                "hook.py",
            ),
        },
        content_type="multipart/form-data",
    )
    # PRG: the POST must 302 to /success, stashing the rich context.
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]

    # The smart-group NOTICE must survive the one-shot flash and render
    # on the redirected GET — proving the rich context, not just the
    # generic success_msg, crosses the redirect.
    page = logged_in_client.get("/success")
    assert page.status_code == 200
    assert b"NOTICE!  This webhook is not yet enabled." in page.data


def test_success_has_forward_actions_not_history_back(
    logged_in_client, jawa_env
):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    resp = logged_in_client.get("/success")
    body = resp.data.decode()
    # No blind history.back() — it walks into a spent form.
    assert "history.back()" not in body
    # Forward actions present: Create another (for this type) + Dashboard.
    assert "/automations/custom/new" in body  # Create another
    assert "/dashboard" in body  # Dashboard


# --- Jamf Pro webhook XML: every interpolated value must be escaped ---


def test_auth_xml_escapes_the_basic_credentials():
    """A password that closes its own element must not inject siblings.

    _build_webhook_xml already escapes name and event with a comment
    explaining why hand-built f-string XML has to. _build_auth_xml, in
    the same file, interpolated raw form values -- so a crafted password
    could add a second <url> element to the <webhook> object, pointing
    Jamf Pro's event deliveries at another host while JAWA's own record
    and success page still showed the JAWA callback URL.
    """
    from views._type_handlers.jamf_handler import _build_auth_xml

    hostile = (
        "s3cret</password><url>https://attacker.example/hooks/x</url>"
        "<password>s3cret"
    )
    xml = _build_auth_xml(
        {
            "choice": "basic",
            "basic_username": "admin",
            "basic_password": hostile,
        }
    )
    assert "<url>" not in xml, f"injected a <url> element: {xml}"
    assert "attacker.example" not in xml or "&lt;url&gt;" in xml
    assert xml.count("<password>") == 1, f"injected a second element: {xml}"


def test_auth_xml_survives_an_ordinary_ampersand():
    """The benign case needs no malice: & alone made Jamf reject the body."""
    from views._type_handlers.jamf_handler import _build_auth_xml

    xml = _build_auth_xml(
        {
            "choice": "basic",
            "basic_username": "a&b",
            "basic_password": "p<q>r",
        }
    )
    assert "<username>a&amp;b</username>" in xml
    assert "<password>p&lt;q&gt;r</password>" in xml


# --- Detail page clarity ---


def _keyed_custom_data(name="HelpdeskTicket", key="s3cret-key-value"):
    return {
        "custom_name": name,
        "description": "ticket hook",
        "custom": "custom",
        "api_key": key,
        "new_file": (
            io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
            "hook.py",
        ),
    }


def test_custom_detail_shows_endpoint(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_keyed_custom_data(),
        content_type="multipart/form-data",
    )
    success = logged_in_client.get("/success").data.decode()
    assert "https://jawa.example.test/hooks/HelpdeskTicket" in success
    assert "Send POST requests to:" in success
    # The one place the key is shown, and never as a Python dict.
    assert "s3cret-key-value" in success
    assert "{'" not in success

    detail = logged_in_client.get(
        "/automations/custom/HelpdeskTicket"
    ).data.decode()
    assert "https://jawa.example.test/hooks/HelpdeskTicket" in detail
    assert "x-api-key header" in detail
    assert "s3cret-key-value" not in detail
    assert "curl -X POST" in detail
    assert 'class="copy-btn"' in detail


def test_custom_detail_without_server_address_links_to_setup(
    logged_in_client, jawa_env
):
    jawa_env.server_file.write_text("{}")
    jawa_env.add_webhook(
        {
            "name": "NoAddress",
            "tag": "custom",
            "script": str(jawa_env.scripts_dir / "x.sh"),
            "api_key": "null",
        }
    )
    body = logged_in_client.get("/automations/custom/NoAddress").data.decode()
    assert "Set the JAWA server address in Setup" in body
    assert 'href="/setup"' in body


# --- Timed automations ---


class _Tab:
    """Builds a CronTab over fixed text that never touches the system."""

    def __init__(self, text=""):
        from crontab import CronTab

        class Memory(CronTab):
            def write(self, *args, **kwargs):
                self.written = True

        self._cls = Memory
        self.text = text

    def __call__(self, user=None):
        return self._cls(tab=self.text)


def _add_cron(jawa_env, **overrides):
    entry = {
        "name": "NightlyExport",
        "description": "export",
        "frequency": "Every day at 2:00 AM",
        "script": str(jawa_env.scripts_dir / "cron_NightlyExport.sh"),
    }
    entry.update(overrides)
    data = json.loads(jawa_env.cron_file.read_text())
    data.append(entry)
    jawa_env.cron_file.write_text(json.dumps(data))


def test_cron_detail_shows_readable_schedule(
    logged_in_client, jawa_env, monkeypatch
):
    from views._type_handlers import cron_handler

    monkeypatch.setattr(
        cron_handler, "CronTab", _Tab("0 2 * * * /bin/true # NightlyExport\n")
    )
    resp = logged_in_client.post(
        "/automations/cron/new",
        data={
            "cron_name": "Created",
            "frequency": "everyday",
            "daytime": "2",
            "script": (io.BytesIO(b"#!/bin/sh\ntrue\n"), "job.sh"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    stored = json.loads(jawa_env.cron_file.read_text())[0]
    assert stored["frequency"] == "Every day at 2:00 AM"

    _add_cron(jawa_env)
    body = logged_in_client.get(
        "/automations/cron/NightlyExport"
    ).data.decode()
    assert "Every day at 2:00 AM" in body
    assert "Next run" in body
    assert "(server time)" in body

    # An entry saved before labels existed falls back to the crontab line.
    _add_cron(jawa_env, name="OldEntry", frequency="everyday")
    monkeypatch.setattr(
        cron_handler,
        "CronTab",
        _Tab("0 2 * * * /bin/true # OldEntry\n"),
    )
    body = logged_in_client.get("/automations/cron/OldEntry").data.decode()
    assert "0 2 * * *" in body

    # No crontab line means the job is not running.
    monkeypatch.setattr(cron_handler, "CronTab", _Tab(""))
    body = logged_in_client.get(
        "/automations/cron/NightlyExport"
    ).data.decode()
    assert "Not scheduled" in body
    assert "Next run" not in body


def test_cron_edit_form_names_the_current_schedule(
    logged_in_client, jawa_env, monkeypatch
):
    _add_cron(jawa_env)
    body = logged_in_client.get(
        "/automations/cron/NightlyExport/edit"
    ).data.decode()
    assert "Keep current (Every day at 2:00 AM)" in body


# --- Script view ---


def _script_automation(jawa_env, script_path, name="ScriptHook"):
    jawa_env.add_webhook(
        {
            "name": name,
            "tag": "custom",
            "script": str(script_path),
            "api_key": "null",
        }
    )


def test_detail_shows_masked_script(logged_in_client, jawa_env):
    script = jawa_env.scripts_dir / "mask.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        'client_id = "visible-id"\n'
        'client_secret = "abc123"\n'
        "print('done')\n"
    )
    _script_automation(jawa_env, script)
    body = logged_in_client.get("/automations/custom/ScriptHook").data.decode()
    assert "visible-id" in body
    assert "print(&#39;done&#39;)" in body
    assert "********" in body
    assert "abc123" not in body
    assert "Secrets are hidden." in body
    assert "mask.py, 4 lines" in body


def test_script_masking_covers_shell_and_dict_styles():
    from views.automation_view import mask_secrets

    text = (
        "API_TOKEN=abc123\n"
        'export DB_PASSWORD="hunter2"\n'
        "{'api_key': 'k-999', \"name\": \"keep\"}\n"
        "token = get_token()\n"
    )
    masked = mask_secrets(text)
    for leaked in ("abc123", "hunter2", "k-999"):
        assert leaked not in masked
    assert "keep" in masked
    assert "get_token()" in masked


def test_script_outside_scripts_dir_is_not_read(
    logged_in_client, jawa_env, tmp_path_factory
):
    outside = tmp_path_factory.mktemp("elsewhere") / "private.sh"
    outside.write_text("#!/bin/sh\necho outside-marker\n")
    _script_automation(jawa_env, outside)
    body = logged_in_client.get("/automations/custom/ScriptHook").data.decode()
    assert "outside-marker" not in body
    assert "not shown" in body


def test_missing_script_says_so(logged_in_client, jawa_env):
    _script_automation(jawa_env, jawa_env.scripts_dir / "gone.sh")
    body = logged_in_client.get("/automations/custom/ScriptHook").data.decode()
    assert "Script file not found" in body
    assert "gone.sh" in body


# --- Jamf Pro status ---


def _jamf_automation(jawa_env, event="SmartGroupComputerMembershipChange"):
    jawa_env.add_webhook(
        {
            "name": "GroupHook",
            "tag": "jamfpro",
            "url": "https://jamf.example.test",
            "event": event,
            "jamf_id": "77",
            "script": str(jawa_env.scripts_dir / "g.sh"),
            "api_key": "null",
        }
    )


def _fake_webhook_get(monkeypatch, payload=None, raises=None):
    import requests

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if raises:
            raise raises
        resp = requests.Response()
        resp.status_code = 200
        resp.json = lambda: payload
        return resp

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def test_jamf_detail_flags_a_smart_group_automation_that_is_off(
    logged_in_client, jawa_env, monkeypatch
):
    _jamf_automation(jawa_env)
    calls = _fake_webhook_get(
        monkeypatch, {"webhook": {"id": 77, "enabled": False}}
    )
    body = logged_in_client.get("/automations/jamfpro/GroupHook").data.decode()
    assert "Not enabled in Jamf Pro" in body
    assert "Choose a Smart Group" in body
    assert calls[0][0].endswith("/JSSResource/webhooks/id/77")
    assert calls[0][1]["timeout"] == 5
    # The dashboard reads the remembered state and makes no API calls.
    stored = json.loads(jawa_env.webhooks_file.read_text())[0]
    assert stored["jamf_enabled"] is False
    dash = logged_in_client.get("/dashboard").data.decode()
    assert "Off in Jamf Pro" in dash


def test_jamf_detail_shows_enabled(logged_in_client, jawa_env, monkeypatch):
    _jamf_automation(jawa_env, event="ComputerCheckIn")
    _fake_webhook_get(monkeypatch, {"webhook": {"id": 77, "enabled": True}})
    body = logged_in_client.get("/automations/jamfpro/GroupHook").data.decode()
    assert "Enabled" in body
    assert "Not enabled in Jamf Pro" not in body


def test_jamf_detail_survives_a_timeout(
    logged_in_client, jawa_env, monkeypatch
):
    import requests

    _jamf_automation(jawa_env)
    _fake_webhook_get(monkeypatch, raises=requests.exceptions.Timeout())
    resp = logged_in_client.get("/automations/jamfpro/GroupHook")
    assert resp.status_code == 200
    assert "Could not check Jamf Pro" in resp.data.decode()


# --- Sample events ---


class _SamplePopen:
    calls = []

    def __init__(self, args, stdout=None, stderr=None, **kwargs):
        _SamplePopen.calls.append(args)
        self.stdout = io.BytesIO(b"sample ran ok\n")

    def wait(self):
        return 0


def test_send_sample_event_runs_script_with_catalog_example(
    logged_in_client, jawa_env, monkeypatch
):
    import subprocess

    from bin.data_store import get_webhook_schemas

    _SamplePopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", _SamplePopen)
    _jamf_automation(jawa_env, event="ComputerCheckIn")
    _fake_webhook_get(monkeypatch, {"webhook": {"enabled": True}})
    resp = logged_in_client.post("/automations/jamfpro/GroupHook/test")
    assert resp.status_code == 200
    assert len(_SamplePopen.calls) == 1
    example = get_webhook_schemas()["examples"]["ComputerCheckIn"]
    assert json.loads(_SamplePopen.calls[0][1]) == example
    body = resp.data.decode()
    assert "sample ran ok" in body
    assert "Succeeded" in body


def test_send_sample_event_without_example_says_so(
    logged_in_client, jawa_env, monkeypatch
):
    import subprocess

    _SamplePopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", _SamplePopen)
    _jamf_automation(jawa_env, event="NoSuchEvent")
    resp = logged_in_client.post("/automations/jamfpro/GroupHook/test")
    assert "No sample for this event" in resp.data.decode()
    assert _SamplePopen.calls == []


def test_detail_confirms_before_running_a_sample(
    logged_in_client, jawa_env, monkeypatch
):
    _jamf_automation(jawa_env, event="ComputerCheckIn")
    _fake_webhook_get(monkeypatch, {"webhook": {"enabled": True}})
    body = logged_in_client.get("/automations/jamfpro/GroupHook").data.decode()
    assert "Send sample event" in body
    assert 'data-confirm-run="GroupHook"' in body
    assert "onsubmit" not in body
    with open("static/js/confirm.js", encoding="utf-8") as handle:
        assert "runs the real script" in handle.read()
    assert "/log/home.html?q=GroupHook" in body


def test_success_page_renders_headers_as_labelled_fields(
    logged_in_client, jawa_env
):
    logged_in_client.post(
        "/automations/custom/new",
        data=_keyed_custom_data(name="KeyedHook", key="k-12345"),
        content_type="multipart/form-data",
    )
    body = logged_in_client.get("/success").data.decode()
    assert "{'" not in body
    assert "<b>x-api-key</b>" in body
    assert "k-12345" in body


def test_jamf_status_survives_a_null_or_non_object_body(
    logged_in_client, jawa_env, monkeypatch
):
    _jamf_automation(jawa_env)
    for payload in ({"webhook": None}, [1, 2], "text", {"webhook": [1]}):
        _fake_webhook_get(monkeypatch, payload)
        resp = logged_in_client.get("/automations/jamfpro/GroupHook")
        assert resp.status_code == 200
        assert "Could not check Jamf Pro" in resp.data.decode()


def test_cron_detail_has_no_runs_section(
    logged_in_client, jawa_env, monkeypatch
):
    from views._type_handlers import cron_handler

    monkeypatch.setattr(cron_handler, "CronTab", _Tab(""))
    _add_cron(jawa_env)
    body = logged_in_client.get(
        "/automations/cron/NightlyExport"
    ).data.decode()
    assert "Recent runs" not in body
    assert "No runs recorded yet" not in body


def test_renaming_an_automation_moves_its_runs(logged_in_client, jawa_env):
    from bin import data_store

    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    data_store.record_run("prg-test-hook", "2026-01-01T00:00:00", 1, 0, "ok")
    logged_in_client.post(
        "/automations/custom/prg-test-hook/edit",
        data={"custom_name": "renamed-hook"},
        content_type="multipart/form-data",
    )
    assert len(data_store.get_runs("renamed-hook")) == 1
    assert data_store.get_runs("prg-test-hook") == []


def test_malformed_run_history_does_not_break_pages(
    logged_in_client, jawa_env
):
    jawa_env.runs_file.write_text(
        '{"x": [1], "y": 5, "z": [{"exit_code": 1}]}'
    )
    jawa_env.add_webhook(
        {"name": "x", "tag": "custom", "script": "/s/x.sh", "api_key": "null"}
    )
    for path in ("/dashboard", "/automations", "/automations/custom/x"):
        assert logged_in_client.get(path).status_code == 200


def _jamf_create_form(name="refresh-hook"):
    return {
        "webhook_name": name,
        "event": "ComputerAdded",
        "description": "refresh test",
        "choice": "none",
        "new_file": (
            io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
            "hook.py",
        ),
    }


def test_jamf_create_refreshes_an_expired_token(
    logged_in_client, jawa_env, jamf_fake_http, monkeypatch
):
    Resp, default_post = jamf_fake_http
    sent = []

    def _post(url, **kwargs):
        if url.endswith("/api/v1/auth/keep-alive"):
            return Resp(
                {"token": "FRESH", "expires": "2099-01-01T00:00:00.000+0000"}
            )
        if "/JSSResource/webhooks/id/0" in url:
            sent.append(kwargs["headers"]["Authorization"])
            return Resp(
                {}, status_code=201, text="<webhook><id>5</id></webhook>"
            )
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests, "post", _post)
    soon = (datetime.now(timezone.utc) + timedelta(seconds=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.000%z"
    )
    with logged_in_client.session_transaction() as sess:
        sess["token"] = "EXPIRING"
        sess["expires"] = soon
    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data=_jamf_create_form(),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert sent == ["Bearer FRESH"]


def test_jamf_delete_keeps_record_when_jamf_refuses(
    logged_in_client, jawa_env, monkeypatch
):
    _jamf_automation(jawa_env)
    script = jawa_env.scripts_dir / "g.sh"
    script.write_text("#!/bin/sh\n")

    class _Refused:
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr(requests, "put", lambda *a, **k: _Refused())
    resp = logged_in_client.post("/automations/jamfpro/GroupHook/delete")
    assert resp.status_code == 200
    assert b"Jamf Pro refused to disable the webhook" in resp.data
    names = [w["name"] for w in json.loads(jawa_env.webhooks_file.read_text())]
    assert "GroupHook" in names
    assert script.exists()


def test_jamf_delete_keeps_record_when_jamf_is_unreachable(
    logged_in_client, jawa_env, monkeypatch
):
    _jamf_automation(jawa_env)

    def _boom(*_a, **_k):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(requests, "put", _boom)
    resp = logged_in_client.post("/automations/jamfpro/GroupHook/delete")
    assert b"Could not reach Jamf Pro" in resp.data
    names = [w["name"] for w in json.loads(jawa_env.webhooks_file.read_text())]
    assert "GroupHook" in names


def test_okta_create_sends_the_minted_secret(
    logged_in_client, jawa_env, monkeypatch
):
    import io
    import json

    sent = []

    class _Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        if url.endswith("/lifecycle/verify"):
            return _Resp({})
        return _Resp({"id": "hook123"})

    monkeypatch.setattr(requests, "post", fake_post)
    resp = logged_in_client.post(
        "/automations/okta/new",
        data={
            "webhookname": "oktahook",
            "okta_server": "https://okta.example.com",
            "token": "tok",
            "event": "user.lifecycle.deactivate",
            "script": (io.BytesIO(b"#!/bin/sh\necho hi\n"), "hook.sh"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    create = [kw for url, kw in sent if url.endswith("/api/v1/eventHooks")]
    value = json.loads(create[0]["data"])["channel"]["config"]["authScheme"][
        "value"
    ]
    assert value != "${api_key}"
    assert len(value) >= 32
    stored = json.loads(jawa_env.webhooks_file.read_text())
    assert stored[0]["okta_secret"] == value


@pytest.mark.parametrize(
    "auto_type, field, bad_name, message",
    [
        ("custom", "custom_name", "bravo", "already exists"),
        ("custom", "custom_name", "x/y", "letters, numbers"),
        ("custom", "custom_name", "x/y z<", "letters, numbers"),
        ("custom", "custom_name", "NightlyExport", "already exists"),
        ("jamfpro", "webhook_name", "bravo", "already exists"),
        ("jamfpro", "webhook_name", "x/y", "letters, numbers"),
        ("cron", "cron_name", "NightlyExport", "already exists"),
        ("cron", "cron_name", "bravo", "already exists"),
        ("cron", "cron_name", "x/y", "letters, numbers"),
    ],
)
def test_edit_rename_rejects_taken_and_invalid_names(
    logged_in_client, jawa_env, auto_type, field, bad_name, message
):
    jawa_env.add_webhook(
        {
            "name": "alpha",
            "tag": auto_type if auto_type != "cron" else "custom",
            "event": "ComputerAdded",
            "script": "x",
            "description": "d",
            "webhook_username": "null",
            "webhook_password": "null",
            "api_key": "null",
        }
    )
    jawa_env.add_webhook(
        {
            "name": "bravo",
            "tag": "custom",
            "script": "x",
            "description": "d",
            "webhook_username": "null",
            "webhook_password": "null",
            "api_key": "null",
        }
    )
    _add_cron(jawa_env)
    current = "NightlyExport" if auto_type == "cron" else "alpha"
    if auto_type == "cron" and bad_name == "NightlyExport":
        _add_cron(jawa_env, name="Other")
        current = "Other"
    webhooks_before = jawa_env.webhooks_file.read_text()
    cron_before = jawa_env.cron_file.read_text()

    resp = logged_in_client.post(
        f"/automations/{auto_type}/{current}/edit",
        data={field: bad_name, "description": "d"},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    assert message in resp.get_data(as_text=True)
    assert jawa_env.webhooks_file.read_text() == webhooks_before
    assert jawa_env.cron_file.read_text() == cron_before
