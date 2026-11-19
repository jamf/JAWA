"""Device-facing /tap/<service-name> receiver.

GET renders the confirmation page from the query string only; POST is
the only thing that spawns a script. Popen is stubbed, so the whole
request -> token -> payload -> execute pipeline runs without a script.
"""

import io
import json
import subprocess

import pytest

from webhook import tap_receiver as ssr


class RecordingPopen:
    """Stands in for subprocess.Popen; exit code is class-configurable."""

    calls = []
    return_code = 0

    def __init__(self, args, stdout=None, stderr=None, **kwargs):
        RecordingPopen.calls.append(args)
        self.stdout = io.BytesIO(b"script ran\n")

    def wait(self):
        return RecordingPopen.return_code


@pytest.fixture()
def fake_popen(monkeypatch):
    RecordingPopen.calls = []
    RecordingPopen.return_code = 0
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    return RecordingPopen


TOKEN = "t0k3n-abc"


def _make_service(jawa_env, **overrides):
    entry = {
        "name": "reset-ipad",
        "tag": "tap",
        "url": "https://jamf.example.test",
        "jawa_admin": "pytest-admin",
        "script": str(jawa_env.scripts_dir / "reset.py"),
        "description": "harness Tap Action",
        "token": TOKEN,
        "device_family": "mobile",
        "page_title": "Reset {DEVICENAME}?",
        "page_description": "This device will erase itself.",
        "confirm_label": "Erase and reset",
        "success_message": "Done. Put {DEVICENAME} down.",
        "failure_message": "Could not reset. Tell IT.",
        "jamf_id": None,
        "profile_status": "skipped",
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }
    entry.update(overrides)
    jawa_env.add_webhook(entry)
    return entry


GOOD_QUERY = {
    "token": TOKEN,
    "id": "42",
    "udid": "00008030-000A1B2C3D4E5F67",
    "DEVICENAME": "iPad-042",
}


# --- pure helpers ---


def test_fill_placeholders_substitutes_known_and_blanks_unknown():
    out = ssr.fill_placeholders(
        "Reset {DEVICENAME} ({SERIAL})?", {"DEVICENAME": "iPad-1"}
    )
    assert out == "Reset iPad-1 ()?"


def test_parse_device_request_lifts_reserved_and_keeps_the_rest():
    jss_id, udid, params = ssr.parse_device_request(GOOD_QUERY)
    assert jss_id == 42
    assert udid == "00008030-000A1B2C3D4E5F67"
    assert params == {"DEVICENAME": "iPad-042"}


@pytest.mark.parametrize("missing", ["id", "udid"], ids=["no-id", "no-udid"])
def test_parse_device_request_requires_id_and_udid(missing):
    query = dict(GOOD_QUERY)
    del query[missing]
    with pytest.raises(ssr.TapActionRequestError) as excinfo:
        ssr.parse_device_request(query)
    assert excinfo.value.status == 400


def test_parse_device_request_rejects_non_integer_id():
    with pytest.raises(ssr.TapActionRequestError) as excinfo:
        ssr.parse_device_request(dict(GOOD_QUERY, id="42; drop"))
    assert excinfo.value.status == 400


def test_token_matches_is_exact_and_never_accepts_empty():
    service = {"token": TOKEN}
    assert ssr.token_matches(service, TOKEN)
    assert not ssr.token_matches(service, "")
    assert not ssr.token_matches(service, None)
    assert not ssr.token_matches(service, TOKEN + "x")
    assert not ssr.token_matches({"token": ""}, "")


def test_build_payload_has_the_documented_shape():
    service = {"name": "reset-ipad", "device_family": "mobile"}
    payload = ssr.build_tap_payload(
        service, 42, "UDID-1", {"DEVICENAME": "iPad-042"}, "10.0.0.9"
    )
    assert payload["webhook"]["webhookEvent"] == "TapAction"
    assert payload["webhook"]["name"] == "reset-ipad"
    assert isinstance(payload["webhook"]["eventTimestamp"], int)
    assert payload["event"] == {
        "jssID": 42,
        "udid": "UDID-1",
        "deviceType": "mobile",
        "params": {"DEVICENAME": "iPad-042"},
        "remoteAddress": "10.0.0.9",
    }
    assert "token" not in json.dumps(payload)


# --- GET: confirmation page ---


def test_get_renders_confirmation_with_filled_placeholders(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    resp = client.get("/tap/reset-ipad", query_string=GOOD_QUERY)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Reset iPad-042?" in body
    assert "Erase and reset" in body
    # Hidden fields carry every parameter back on the POST.
    assert 'name="token"' in body and TOKEN in body
    assert 'name="id"' in body and 'value="42"' in body
    assert 'name="udid"' in body
    assert 'name="DEVICENAME"' in body
    # The token sits in the page URL; keep it out of the Referer
    # header sent to any CDN asset the layout loads.
    assert 'name="referrer"' in body
    # GET never runs anything.
    assert fake_popen.calls == []


def test_get_accepts_semicolon_separated_query(client, jawa_env, fake_popen):
    """The web clip URL Jamf deploys uses ';' between parameters (Jamf
    rejects '&' inside a web clip payload), and Werkzeug only splits
    on '&' -- so the receiver parses the raw query string itself."""
    _make_service(jawa_env)
    resp = client.get(
        "/tap/reset-ipad?token="
        + TOKEN
        + ";id=42;udid=00008030-000A1B2C3D4E5F67;DEVICENAME=iPad%20042"
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Reset iPad 042?" in body
    assert 'value="42"' in body


def test_get_still_accepts_ampersand_separated_query(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    resp = client.get(
        "/tap/reset-ipad?token="
        + TOKEN
        + "&id=42&udid=00008030-000A1B2C3D4E5F67&DEVICENAME=iPad-042"
    )
    assert resp.status_code == 200
    assert "Reset iPad-042?" in resp.get_data(as_text=True)


def test_confirm_button_disables_itself_on_submit(
    client, jawa_env, fake_popen
):
    """A double tap sent the erase command twice on the first live test
    (two POSTs 1.4 s apart); the form disables its button on submit."""
    _make_service(jawa_env)
    body = client.get("/tap/reset-ipad", query_string=GOOD_QUERY).get_data(
        as_text=True
    )
    assert "button.disabled = true" in body
    assert "addEventListener('submit'" in body


def test_get_escapes_query_values(client, jawa_env, fake_popen):
    _make_service(jawa_env)
    resp = client.get(
        "/tap/reset-ipad",
        query_string=dict(GOOD_QUERY, DEVICENAME="<img src=x>"),
    )
    body = resp.get_data(as_text=True)
    assert "<img src=x>" not in body
    assert "&lt;img src=x&gt;" in body


def test_get_with_wrong_token_is_401_and_does_not_echo_the_name(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    resp = client.get(
        "/tap/reset-ipad", query_string=dict(GOOD_QUERY, token="nope")
    )
    assert resp.status_code == 401
    assert "reset-ipad" not in resp.get_data(as_text=True)


def test_bad_requests_render_a_readable_problem_page(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    query = dict(GOOD_QUERY)
    del query["udid"]
    resp = client.get("/tap/reset-ipad", query_string=query)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert resp.mimetype == "text/html"
    assert "This button is not set up correctly" in body
    assert "Ask your IT team to check this web clip." in body
    assert "missing the device id or UDID" in body
    assert "<svg" in body

    resp = client.get(
        "/tap/reset-ipad", query_string=dict(GOOD_QUERY, token="nope")
    )
    body = resp.get_data(as_text=True)
    assert resp.status_code == 401
    assert "no longer works" in body
    assert "reset-ipad" not in body
    # No console chrome or version string on a device page.
    assert "Discover what" not in body


def test_rate_limited_post_renders_a_problem_page(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    ssr.reset_rate_limits()
    last = None
    for _ in range(ssr.RATE_LIMIT + 1):
        last = client.post("/tap/reset-ipad", data=GOOD_QUERY)
    assert last.status_code == 429
    assert "Please wait a moment" in last.get_data(as_text=True)
    ssr.reset_rate_limits()


def test_device_pages_use_the_brand_name_and_no_console_chrome(
    client, jawa_env, fake_popen
):
    import json

    from bin import data_store

    with open(data_store.SERVER_FILE, "w") as handle:
        json.dump({"brand": "Example School"}, handle)
    _make_service(jawa_env)
    body = client.get("/tap/reset-ipad", query_string=GOOD_QUERY).get_data(
        as_text=True
    )
    assert "Example School" in body
    assert "viewport-fit=cover" in body
    assert "Discover what" not in body
    assert "Jamf Automation" not in body
    assert "main.css" not in body


def test_get_unknown_service_is_401(client, jawa_env, fake_popen):
    resp = client.get("/tap/ghost", query_string=GOOD_QUERY)
    assert resp.status_code == 401


def test_get_without_udid_is_400(client, jawa_env, fake_popen):
    _make_service(jawa_env)
    query = dict(GOOD_QUERY)
    del query["udid"]
    resp = client.get("/tap/reset-ipad", query_string=query)
    assert resp.status_code == 400


def test_get_with_non_ascii_token_is_401_not_500(client, jawa_env, fake_popen):
    """hmac.compare_digest raises TypeError on non-ASCII str input;
    token_matches must compare as bytes so a bad token is a 401, not
    an unhandled 500."""
    _make_service(jawa_env)
    resp = client.get(
        "/tap/reset-ipad", query_string=dict(GOOD_QUERY, token="☃")
    )
    assert resp.status_code == 401
    assert fake_popen.calls == []


def test_get_with_non_ascii_unicode_digit_id_is_400_not_500(
    client, jawa_env, fake_popen
):
    """str.isdigit() accepts Unicode digits (e.g. '²') that
    int() rejects; parse_device_request must reject them as 400
    rather than raising ValueError."""
    _make_service(jawa_env)
    resp = client.get("/tap/reset-ipad", query_string=dict(GOOD_QUERY, id="²"))
    assert resp.status_code == 400
    assert fake_popen.calls == []


def test_non_tap_entry_is_not_a_service(client, jawa_env, fake_popen):
    _make_service(jawa_env, tag="custom")
    resp = client.get("/tap/reset-ipad", query_string=GOOD_QUERY)
    assert resp.status_code == 401


def test_tap_entry_cannot_be_fired_through_hooks(client, jawa_env, fake_popen):
    """The three "null" auth keys would otherwise make /hooks/<name>
    an open, token-free way to run a Tap Action script."""
    _make_service(jawa_env)
    resp = client.post("/hooks/reset-ipad", json={"webhook": {}})
    assert resp.status_code == 401
    assert fake_popen.calls == []


# --- POST: run ---


def test_post_runs_script_with_the_contract_payload(
    client, jawa_env, fake_popen
):
    entry = _make_service(jawa_env)
    resp = client.post("/tap/reset-ipad", data=GOOD_QUERY)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Done. Put iPad-042 down." in body
    assert 'name="referrer"' in body
    assert len(fake_popen.calls) == 1
    argv = fake_popen.calls[0]
    assert argv[0] == entry["script"]
    payload = json.loads(argv[1])
    assert payload["webhook"]["webhookEvent"] == "TapAction"
    assert payload["webhook"]["name"] == "reset-ipad"
    assert payload["event"]["jssID"] == 42
    assert payload["event"]["udid"] == GOOD_QUERY["udid"]
    assert payload["event"]["deviceType"] == "mobile"
    assert payload["event"]["params"] == {"DEVICENAME": "iPad-042"}
    assert "token" not in argv[1]


def test_post_failure_renders_failure_message_with_500(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    fake_popen.return_code = 20
    resp = client.post("/tap/reset-ipad", data=GOOD_QUERY)
    assert resp.status_code == 500
    body = resp.get_data(as_text=True)
    assert "Could not reset. Tell IT." in body
    assert "script ran" not in body  # never the script output


def test_post_with_bad_token_is_401_and_runs_nothing(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    resp = client.post("/tap/reset-ipad", data=dict(GOOD_QUERY, token="nope"))
    assert resp.status_code == 401
    assert fake_popen.calls == []


def test_post_without_id_is_400_and_runs_nothing(client, jawa_env, fake_popen):
    _make_service(jawa_env)
    data = dict(GOOD_QUERY)
    del data["id"]
    resp = client.post("/tap/reset-ipad", data=data)
    assert resp.status_code == 400
    assert fake_popen.calls == []


# --- getting back to the start page from a full-screen web clip ---------------
# A web clip has no browser chrome: no reload, no pull-to-refresh. After a
# run the person was stuck on the result page, and going back restored the
# confirm page from the back-forward cache with its button still disabled.


def _back_form_fields(body):
    import re

    form = re.search(
        r'<form method="GET" action="/tap/reset-ipad"(.*?)</form>',
        body,
        re.S,
    )
    assert form, "result page has no way back to the start page"
    return dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(1)))


@pytest.mark.parametrize("return_code, status", [(0, 200), (20, 500)])
def test_result_page_links_back_to_the_start_page(
    client, jawa_env, fake_popen, return_code, status
):
    _make_service(jawa_env)
    fake_popen.return_code = return_code
    resp = client.post("/tap/reset-ipad", data=GOOD_QUERY)
    assert resp.status_code == status
    body = resp.get_data(as_text=True)
    assert "Back to start" in body
    fields = _back_form_fields(body)
    assert fields == GOOD_QUERY
    # Following it renders the confirm page again and runs nothing.
    again = client.get("/tap/reset-ipad", query_string=fields)
    assert again.status_code == 200
    assert "Erase and reset" in again.get_data(as_text=True)
    assert len(fake_popen.calls) == 1


def test_confirm_button_is_re_enabled_when_the_page_is_restored(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    body = client.get("/tap/reset-ipad", query_string=GOOD_QUERY).get_data(
        as_text=True
    )
    assert "pageshow" in body
    assert ".disabled = false" in body


def test_rate_limit_ignores_spoofed_forwarded_for(
    client, jawa_env, fake_popen
):
    _make_service(jawa_env)
    ssr.reset_rate_limits()
    codes = []
    for i in range(ssr.RATE_LIMIT + 1):
        resp = client.post(
            "/tap/reset-ipad",
            data=GOOD_QUERY,
            headers={
                "X-Forwarded-For": f"10.0.0.{i}",
                "X-Real-IP": "203.0.113.9",
            },
        )
        codes.append(resp.status_code)
    assert codes[-1] == 429
    ssr.reset_rate_limits()


def test_remote_address_falls_back_to_the_connection(client, jawa_env):
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "10.9.9.9"},
        environ_base={"REMOTE_ADDR": "198.51.100.4"},
    ):
        assert ssr._remote_address() == "198.51.100.4"
    with app.test_request_context(
        "/",
        headers={"X-Real-IP": "203.0.113.9"},
        environ_base={"REMOTE_ADDR": "198.51.100.4"},
    ):
        assert ssr._remote_address() == "203.0.113.9"


def test_tap_script_timeout_shows_failure_page(client, jawa_env, monkeypatch):
    monkeypatch.setenv("JAWA_SCRIPT_TIMEOUT", "1")
    script = jawa_env.scripts_dir / "reset.py"
    script.write_text("#!/bin/sh\nsleep 60\n")
    script.chmod(0o755)
    _make_service(jawa_env)
    ssr.reset_rate_limits()
    resp = client.post("/tap/reset-ipad", data=GOOD_QUERY)
    assert resp.status_code == 504
    ssr.reset_rate_limits()
