"""Tap action templates: catalog display and the enable path."""

import json
import os

import pytest

from bin import data_store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO_ROOT, "data", "workflows", "workflow_config.json")


def _catalog():
    with open(CONFIG, "r", encoding="utf-8") as handle:
        return json.load(handle)


TAP = [wf for wf in _catalog() if wf.get("trigger_type") == "tap"]
SLUGS = [wf["slug"] for wf in TAP]


@pytest.fixture(params=TAP, ids=SLUGS)
def tap_workflow(request):
    return request.param


def test_at_least_the_rts_template_is_tap():
    assert "tap-return-to-service" in SLUGS


def test_tap_entry_declares_page_strings_and_family(
    tap_workflow,
):
    block = tap_workflow["tap"]
    assert block["device_family"] in ("mobile", "computer")
    for key in (
        "page_title",
        "page_description",
        "confirm_label",
        "success_message",
        "failure_message",
    ):
        assert block[key].strip(), f"{tap_workflow['slug']} {key}"
    assert tap_workflow.get("trigger_event") is None


def test_catalog_and_detail_label_tap_trigger(
    logged_in_client, jawa_env, tap_workflow
):
    slug = tap_workflow["slug"]
    for path in (
        "/templates",
        f"/templates/{slug}",
        f"/templates/{slug}/enable",
    ):
        body = logged_in_client.get(path).get_data(as_text=True)
        assert "Tap action (web clip)" in body, path
        assert ">None<" not in body


def test_enable_form_shows_page_fields_not_jamf_event(
    logged_in_client, jawa_env, tap_workflow
):
    body = logged_in_client.get(
        f"/templates/{tap_workflow['slug']}/enable"
    ).get_data(as_text=True)
    assert 'name="page_title"' in body
    assert 'name="create_profile"' in body
    assert 'name="event"' not in body
    assert "Webhook Authentication" not in body


def test_enabling_creates_a_tap_record_that_fires(
    logged_in_client, jawa_env, enable_form, monkeypatch
):
    import io
    import subprocess

    calls = []

    class P:
        def __init__(self, args, stdout=None, stderr=None, **kwargs):
            calls.append(args)
            self.stdout = io.BytesIO(b"ok\n")

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", P)

    form = enable_form("tap-return-to-service", webhook_name="reset-ipad")
    resp = logged_in_client.post(
        "/templates/tap-return-to-service/enable", data=form
    )
    assert resp.status_code == 302, resp.get_data(as_text=True)
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry is not None
    assert entry["tag"] == "tap"
    assert entry["device_family"] == "mobile"
    assert entry["page_title"]  # defaults came from the catalog
    assert entry["profile_status"] == "skipped"  # no checkbox in form
    assert os.path.isfile(entry["script"])
    with open(entry["script"], encoding="utf-8") as handle:
        source = handle.read()
    assert "__JAWA_" not in source
    assert form["wifi_profile_name"] in source

    resp = logged_in_client.post(
        "/tap/reset-ipad",
        data={
            "token": entry["token"],
            "id": "7",
            "udid": "UDID-7",
            "DEVICENAME": "iPad-7",
        },
    )
    assert resp.status_code == 200
    assert calls and calls[0][0] == entry["script"]
    payload = json.loads(calls[0][1])
    assert payload["event"]["jssID"] == 7


def test_enable_overrides_page_strings_from_the_form(
    logged_in_client, jawa_env, enable_form
):
    form = enable_form(
        "tap-return-to-service",
        webhook_name="reset-2",
        page_title="Custom {DEVICENAME}",
    )
    logged_in_client.post("/templates/tap-return-to-service/enable", data=form)
    assert (
        data_store.get_webhook_by_name("reset-2")["page_title"]
        == "Custom {DEVICENAME}"
    )


ASSETS = os.path.join(REPO_ROOT, "data", "workflows", "assets", "brander")


def test_brander_template_and_assets_ship():
    assert "tap-brander" in SLUGS
    for name in (
        "lockscreen-template.png",
        "null.png",
        "brandlogo.png",
        "nursing.png",
        "patient.png",
        "pharmacist.png",
        "technician.png",
        "transport.png",
        "videoconferencing.png",
        "jawa-logo.png",
        "example-template.json",
        "example-ipad-template.json",
        "example-set.json",
        "README.md",
    ):
        assert os.path.isfile(os.path.join(ASSETS, name)), name
    assert not os.path.exists(os.path.join(ASSETS, "SF-Pro.ttf"))


def test_brander_requirements_are_declared():
    path = os.path.join(REPO_ROOT, "requirements.txt")
    with open(path, encoding="utf-8") as handle:
        reqs = handle.read().lower()
    assert "pillow" in reqs
    assert "qrcode" in reqs


def test_brander_script_generates_an_image_without_a_font_file(tmp_path):
    """The image pipeline must work with Pillow's built-in font so the
    template ships with no proprietary font."""
    import importlib.util

    path = os.path.join(
        REPO_ROOT, "data", "workflows", "scripts", "tap_brander.py"
    )
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source = (
        source.replace('"__JAWA_EA_ID__"', "0")
        .replace("__JAWA_EA_ID__", "0")
        .replace("__JAWA_WALLPAPER_SETTING__", "3")
        .replace("__JAWA_MAX_KB__", "1500")
        .replace('"__JAWA_ALLOW_PERSON_FIELDS__"', '"no"')
        # font_path is a required field at enable time, so the deployed
        # script never carries the bare token; "none" is the sentinel
        # value load_font() treats as the built-in font.
        .replace('"__JAWA_FONT_PATH__"', '"none"')
    )
    spec = importlib.util.spec_from_loader("ss_brander", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, path, "exec"), module.__dict__)
    device = {
        "general": {
            "id": 42,
            "device_name": "iPad-042",
            "serial_number": "DMPX1",
            "model": "iPad",
            "os_type": "iPadOS",
            "os_version": "18.0",
        },
        "location": {
            "building": "Main",
            "department": "Nursing",
            "room": "3A",
            "username": "nurse",
        },
    }
    img = module.compose_legacy(
        ASSETS, "lockscreen-template", "Nursing", device
    )
    assert img.size[0] > 100


def _create_tap(client):
    from tests.test_tap_handler import _create_form

    return client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )


def test_tap_success_page_has_no_python_dict_repr(logged_in_client, jawa_env):
    _create_tap(logged_in_client)
    body = logged_in_client.get("/success").data.decode()
    assert "{'" not in body
    assert "<b>URL</b>" in body
    assert 'class="copy-btn"' in body


def test_tap_detail_offers_the_full_url_with_copy(logged_in_client, jawa_env):
    from bin import data_store

    _create_tap(logged_in_client)
    entry = data_store.get_webhook_by_name("reset-ipad")
    body = logged_in_client.get("/automations/tap/reset-ipad").data.decode()
    assert f"token={entry['token']}" in body
    assert 'aria-label="Copy Web clip URL"' in body


def test_tap_row_says_web_clip_and_rejects_sample_events(
    logged_in_client, jawa_env
):
    _create_tap(logged_in_client)
    dash = logged_in_client.get("/dashboard").data.decode()
    assert "Web clip" in dash
    resp = logged_in_client.post("/automations/tap/reset-ipad/test")
    assert "Sample events can only be sent" in resp.data.decode()


# --- device page behaviour and the admin preview ---

_SERVICE = {
    "name": "reset-ipad",
    "tag": "tap",
    "url": "https://jamf.example.test",
    "jawa_admin": "pytest-admin",
    "script": "/nonexistent/reset.sh",
    "description": "preview harness",
    "token": "preview-token-value",
    "device_family": "mobile",
    "cooldown_minutes": 5,
    "page_title": "Clear the cache on {DEVICENAME}",
    "page_description": "Serial {SERIALNUMBER}.",
    "confirm_label": "Clear it",
    "success_message": "Cleared {DEVICENAME}.",
    "failure_message": "Could not clear {DEVICENAME}.",
    "jamf_id": None,
    "profile_status": "skipped",
    "webhook_username": "null",
    "webhook_password": "null",
    "api_key": "null",
}


def test_confirm_page_has_a_progress_live_region(client, jawa_env):
    jawa_env.add_webhook(dict(_SERVICE))
    body = client.get(
        "/tap/reset-ipad",
        query_string={
            "token": _SERVICE["token"],
            "id": "7",
            "udid": "UDID-1",
            "DEVICENAME": "Sample iPad",
        },
    ).get_data(as_text=True)
    assert 'aria-live="polite"' in body
    assert "Working..." in body
    assert "Keep this screen open" in body
    assert "prefers-reduced-motion" in client.get(
        "/static/css/tap.css"
    ).get_data(as_text=True)


@pytest.mark.parametrize(
    "state", ["confirm", "success", "failure", "cooldown"]
)
def test_preview_renders_without_running(
    logged_in_client, jawa_env, monkeypatch, state
):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a))
    jawa_env.add_webhook(dict(_SERVICE))
    resp = logged_in_client.get(
        f"/automations/tap/reset-ipad/preview?state={state}"
    )
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Sample iPad" in body
    assert "{DEVICENAME}" not in body
    assert _SERVICE["token"] not in body
    assert 'action="/tap/' not in body
    assert "&lt;form" in body and "action=" not in body.split("srcdoc=")[1]
    assert "Preview only. Buttons here do not run the script." in body
    assert calls == []


def test_preview_requires_login(client, jawa_env):
    jawa_env.add_webhook(dict(_SERVICE))
    resp = client.get("/automations/tap/reset-ipad/preview")
    assert resp.status_code == 302
    assert "/tap" not in resp.headers["Location"]
