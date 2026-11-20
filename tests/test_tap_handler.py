"""Console side of Tap Action automations: the type handler."""

import io
import plistlib
import xml.etree.ElementTree as ET

import pytest
import requests

from bin import data_store
from views._type_handlers import get_handler
from views._type_handlers import tap_handler as ssh


def _script_upload():
    return (io.BytesIO(b"#!/bin/bash\necho hi\n"), "reset.sh")


def _create_form(**overrides):
    form = {
        "service_name": "reset-ipad",
        "description": "Loaner reset",
        "device_family": "mobile",
        "page_title": "Reset {DEVICENAME}?",
        "page_description": "It will erase itself.",
        "confirm_label": "Erase and reset",
        "success_message": "Done.",
        "failure_message": "Failed. Tell IT.",
        "new_file": _script_upload(),
    }
    form.update(overrides)
    return form


def test_handler_is_registered():
    handler = get_handler("tap")
    assert handler is not None
    assert handler.tag == "tap"
    assert handler.display_name == "Tap Action"


def test_service_url_carries_token_and_reserved_variables():
    url = ssh.service_url("https://jawa.example.test", "reset-ipad", "T")
    assert url.startswith("https://jawa.example.test/tap/reset-ipad?")
    assert "token=T" in url
    assert "id=$JSSID" in url
    assert "udid=$UDID" in url
    assert "DEVICENAME=$DEVICENAME" in url


def test_service_url_never_contains_an_ampersand():
    """Jamf Pro refuses to store a web clip profile whose URL contains
    '&' in any encoding (409 "Unable to update the database", probed
    live 2026-09-21), so parameters are joined with ';'. Reserved
    params come first so a display value cannot disturb them."""
    url = ssh.service_url("https://jawa.example.test", "reset-ipad", "T")
    assert "&" not in url
    query = url.split("?", 1)[1]
    assert query.split(";")[:3] == ["token=T", "id=$JSSID", "udid=$UDID"]


def test_mint_token_is_long_and_unique():
    a, b = ssh.mint_token(), ssh.mint_token()
    assert a != b
    assert len(a) >= 32


def test_create_persists_the_full_record(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302 and "/success" in resp.headers["Location"]
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry is not None
    assert entry["tag"] == "tap"
    assert entry["device_family"] == "mobile"
    assert entry["page_title"] == "Reset {DEVICENAME}?"
    assert entry["failure_message"] == "Failed. Tell IT."
    assert len(entry["token"]) >= 32
    assert entry["script"].endswith("reset-ipad-reset.sh")
    assert entry["jamf_id"] is None
    assert entry["profile_status"] == "skipped"  # no checkbox sent
    for key in ("webhook_username", "webhook_password", "api_key"):
        assert entry[key] == "null"


def test_create_rejects_bad_service_name(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(service_name="reset ipad"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "letters, numbers" in resp.get_data(as_text=True)
    assert data_store.get_webhook_by_name("reset ipad") is None


def test_create_rejects_unknown_device_family(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(device_family="toaster"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert data_store.get_webhook_by_name("reset-ipad") is None


def test_create_requires_every_page_string(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(confirm_label=""),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert data_store.get_webhook_by_name("reset-ipad") is None


def test_detail_shows_the_web_clip_url(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    body = logged_in_client.get("/automations/tap/reset-ipad").get_data(
        as_text=True
    )
    assert "/tap/reset-ipad?token=" + entry["token"] in body
    assert "Device family" in body


def test_edit_updates_strings_and_keeps_the_token(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    before = data_store.get_webhook_by_name("reset-ipad")
    form = _create_form(page_title="Wipe {DEVICENAME}")
    del form["new_file"]
    resp = logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    after = data_store.get_webhook_by_name("reset-ipad")
    assert after["page_title"] == "Wipe {DEVICENAME}"
    assert after["token"] == before["token"]
    assert after["script"] == before["script"]


def test_delete_retires_script_and_removes_record(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    resp = logged_in_client.post("/automations/tap/reset-ipad/delete", data={})
    assert resp.status_code in (200, 302)
    assert data_store.get_webhook_by_name("reset-ipad") is None
    assert (
        jawa_env.scripts_dir / (entry["script"].rsplit("/", 1)[1] + ".old")
    ).exists()


@pytest.mark.parametrize(
    "path",
    ["/automations/tap", "/automations/tap/new"],
)
def test_console_pages_render(logged_in_client, jawa_env, path):
    assert logged_in_client.get(path).status_code == 200


class _ProfileJamf:
    """Captures profile calls and answers like Jamf Pro Classic API."""

    def __init__(self, fake_response_cls, fake_post, status=201):
        self._fake_response_cls = fake_response_cls
        self._fake_post = fake_post
        self.posts = []
        self.puts = []
        self.status = status
        self.put_status = 201

    def post(self, url, **kwargs):
        if "/JSSResource/mobiledeviceconfigurationprofiles/id/0" in url:
            self.posts.append((url, kwargs))
            return self._fake_response_cls(
                {},
                status_code=self.status,
                text="<configuration_profile><id>55</id>"
                "</configuration_profile>",
            )
        return self._fake_post(url, **kwargs)

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return self._fake_response_cls(
            {}, status_code=self.put_status, text="<id>55</id>"
        )


@pytest.fixture()
def profile_jamf(monkeypatch, fake_jamf, jamf_fake_http):
    fake_response_cls, fake_post = jamf_fake_http
    jamf = _ProfileJamf(fake_response_cls, fake_post)
    monkeypatch.setattr(requests, "post", jamf.post)
    monkeypatch.setattr(requests, "put", jamf.put)
    return jamf


def test_plist_is_a_managed_web_clip_with_the_service_url():
    entry = {"name": "reset-ipad", "page_title": "Reset {DEVICENAME}?"}
    url = "https://jawa.example.test/tap/reset-ipad?token=T&id=$JSSID"
    plist = plistlib.loads(ssh.build_webclip_plist(entry, url).encode())
    assert plist["PayloadType"] == "Configuration"
    clip = plist["PayloadContent"][0]
    assert clip["PayloadType"] == "com.apple.webClip.managed"
    assert clip["URL"] == url
    assert clip["Label"] == "Reset?"  # placeholders stripped
    assert clip["IsRemovable"] is False
    assert clip["FullScreen"] is True
    assert clip["PayloadIdentifier"] == "com.jamf.jawa.tap.reset-ipad.webclip"


def test_plist_web_clip_icon_is_the_jawa_logo():
    """The home-screen icon defaults to the JAWA logo, a precomposed
    180x180 PNG embedded as data."""
    import io

    from PIL import Image

    entry = {"name": "reset-ipad", "page_title": "Reset"}
    plist = plistlib.loads(
        ssh.build_webclip_plist(entry, "https://x/").encode()
    )
    icon = plist["PayloadContent"][0]["Icon"]
    assert isinstance(icon, bytes)
    with Image.open(io.BytesIO(icon)) as img:
        assert img.format == "PNG"
        assert img.size == (180, 180)
    assert plist["PayloadContent"][0]["Precomposed"] is True


def test_plist_uuids_are_random_when_the_record_stores_none():
    """Deterministic uuid5 UUIDs collided with a retired profile's when
    a service was deleted and re-created under the same name: Jamf
    keeps the retired profile (renamed, unscoped) and answered 409
    "Duplicate payload uuid" (live, 2026-09-21)."""
    entry = {"name": "reset-ipad", "page_title": "Reset"}
    a = plistlib.loads(ssh.build_webclip_plist(entry, "https://x/").encode())
    b = plistlib.loads(ssh.build_webclip_plist(entry, "https://x/").encode())
    assert a["PayloadUUID"] != b["PayloadUUID"]
    assert (
        a["PayloadContent"][0]["PayloadUUID"]
        != b["PayloadContent"][0]["PayloadUUID"]
    )


def test_plist_uuids_come_from_the_record_when_stored():
    entry = {
        "name": "reset-ipad",
        "page_title": "Reset",
        "profile_uuid": "11111111-2222-4333-8444-555555555555",
        "clip_uuid": "66666666-7777-4888-8999-AAAAAAAAAAAA",
    }
    plist = plistlib.loads(
        ssh.build_webclip_plist(entry, "https://x/").encode()
    )
    assert plist["PayloadUUID"] == entry["profile_uuid"]
    assert plist["PayloadContent"][0]["PayloadUUID"] == entry["clip_uuid"]


def test_create_stores_the_profile_uuids_on_the_record(
    logged_in_client, jawa_env, profile_jamf
):
    import uuid as uuid_mod

    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    uuid_mod.UUID(entry["profile_uuid"])
    uuid_mod.UUID(entry["clip_uuid"])
    _, kwargs = profile_jamf.posts[0]
    assert entry["profile_uuid"] in kwargs["data"]
    assert entry["clip_uuid"] in kwargs["data"]


def test_profile_xml_uses_only_mobile_schema_elements():
    """Jamf Pro's mobiledeviceconfigurationprofiles schema has
    deployment_method; distribution_method belongs to the macOS
    (osxconfigurationprofiles) schema. Sending it makes Jamf answer
    400 "Error in XML file. Possible mismatch between resource
    specified in the URL and XML file" (seen live 2026-09-21)."""
    entry = {"name": "reset-ipad", "page_title": "Reset"}
    root = ET.fromstring(ssh.build_profile_xml(entry, "https://x/"))
    assert root.find("general/distribution_method") is None
    assert root.findtext("general/deployment_method") == (
        "Install Automatically"
    )


def test_profile_xml_is_well_formed_and_unscoped():
    entry = {"name": "reset-ipad", "page_title": "Reset"}
    root = ET.fromstring(ssh.build_profile_xml(entry, "https://x/?a=1&b=2"))
    assert root.tag == "configuration_profile"
    assert (
        root.findtext("general/name") == "JAWA Tap Action: Reset (reset-ipad)"
    )
    assert root.findtext("scope/all_mobile_devices") == "false"
    assert root.findtext("general/redeploy_on_update") == "All"
    payloads = root.findtext("general/payloads")
    assert "com.apple.webClip.managed" in payloads
    assert "a=1&amp;b=2" in payloads  # escaped inside the plist string


def test_profile_xml_names_differ_for_same_title_different_service():
    """Jamf Pro profile names must be unique; two services created from
    the same template share page_title by default, so the service
    name must disambiguate them."""
    entry_a = {"name": "reset-ipad-a", "page_title": "Reset"}
    entry_b = {"name": "reset-ipad-b", "page_title": "Reset"}
    root_a = ET.fromstring(ssh.build_profile_xml(entry_a, "https://x/"))
    root_b = ET.fromstring(ssh.build_profile_xml(entry_b, "https://x/"))
    assert root_a.findtext("general/name") != root_b.findtext("general/name")


def test_create_with_checkbox_creates_profile_and_stores_id(
    logged_in_client, jawa_env, profile_jamf
):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["jamf_id"] == "55"
    assert entry["profile_status"] == "created"
    assert len(profile_jamf.posts) == 1
    url, kwargs = profile_jamf.posts[0]
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert entry["token"] in kwargs["data"]


def test_create_refreshes_the_token_before_posting_the_profile(
    logged_in_client, jawa_env, profile_jamf, monkeypatch
):
    """fresh_token() copies the renewed token into the session_data
    snapshot before the profile request is built, or Jamf Pro gets the
    old token."""

    def _refresh(session_data=None):
        session_data["token"] = "fresh-token"
        return "fresh-token"

    monkeypatch.setattr(ssh, "fresh_token", _refresh)
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    assert len(profile_jamf.posts) == 1
    _url, kwargs = profile_jamf.posts[0]
    assert kwargs["headers"]["Authorization"] == "Bearer fresh-token"


def test_create_without_checkbox_skips_jamf(
    logged_in_client, jawa_env, profile_jamf
):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["profile_status"] == "skipped"
    assert profile_jamf.posts == []


def test_profile_failure_still_creates_the_service(
    logged_in_client, jawa_env, profile_jamf
):
    profile_jamf.status = 409
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry is not None
    assert entry["jamf_id"] is None
    assert entry["profile_status"] == "failed"


def test_edit_updates_the_profile_when_one_exists(
    logged_in_client, jawa_env, profile_jamf
):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    form = _create_form(page_title="Wipe it")
    del form["new_file"]
    logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    assert any(
        "/mobiledeviceconfigurationprofiles/id/55" in url
        for url, _ in profile_jamf.puts
    )


def test_delete_retires_the_profile(logged_in_client, jawa_env, profile_jamf):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    logged_in_client.post("/automations/tap/reset-ipad/delete", data={})
    url, kwargs = profile_jamf.puts[-1]
    assert "/mobiledeviceconfigurationprofiles/id/55" in url
    assert ".old." in kwargs["data"]


def test_computer_family_never_gets_a_mobile_profile(
    logged_in_client, jawa_env, profile_jamf
):
    """Web Clips are a mobile device profile payload; Jamf Pro has no
    computer equivalent, so a computer-family service must be skipped
    even with the checkbox on."""
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(device_family="computer", create_profile="on"),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["jamf_id"] is None
    assert entry["profile_status"] == "skipped"
    assert profile_jamf.posts == []


def test_token_check_failure_still_creates_the_service(
    logged_in_client, jawa_env, profile_jamf, monkeypatch
):
    """A malformed/expired-token check must degrade to
    profile_status "failed", never bubble out of the "never raises"
    profile helpers (and never 500 the create request)."""

    def _boom(*_a, **_k):
        raise ValueError("bad expires value")

    monkeypatch.setattr(ssh, "fresh_token", _boom)
    resp = logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    assert resp.status_code != 500
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry is not None
    assert entry["jamf_id"] is None
    assert entry["profile_status"] == "failed"
    assert profile_jamf.posts == []


def test_edit_marks_the_profile_failed_when_jamf_refuses_the_update(
    logged_in_client, jawa_env, profile_jamf
):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    profile_jamf.put_status = 409
    form = _create_form(page_title="Wipe it")
    del form["new_file"]
    logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["profile_status"] == "failed"


def _png(size):
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (size, size), (200, 30, 30)).save(out, format="PNG")
    out.seek(0)
    return out


def test_webclip_uses_custom_label_and_icon(
    logged_in_client, jawa_env, profile_jamf, monkeypatch, tmp_path
):
    from PIL import Image

    monkeypatch.setattr(ssh, "ICON_DIR", str(tmp_path / "icons"))
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(
            create_profile="on",
            webclip_label="Clear cache",
            webclip_icon=(_png(512), "icon.png"),
        ),
        content_type="multipart/form-data",
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["webclip_label"] == "Clear cache"
    _, kwargs = profile_jamf.posts[0]
    root = ET.fromstring(kwargs["data"])
    plist = plistlib.loads(root.find("general/payloads").text.encode())
    clip = plist["PayloadContent"][0]
    assert clip["Label"] == "Clear cache"
    with Image.open(io.BytesIO(clip["Icon"])) as icon:
        assert icon.format == "PNG"
        assert icon.size == (180, 180)


def test_webclip_without_label_or_icon_keeps_the_defaults(
    logged_in_client, jawa_env, monkeypatch, tmp_path
):
    monkeypatch.setattr(ssh, "ICON_DIR", str(tmp_path / "icons"))
    entry = {"name": "reset-ipad", "page_title": "Reset {DEVICENAME}?"}
    plist = plistlib.loads(
        ssh.build_webclip_plist(entry, "https://x/").encode()
    )
    clip = plist["PayloadContent"][0]
    assert clip["Label"] == "Reset?"
    assert clip["Icon"] == ssh._default_icon()


def test_create_rejects_a_small_icon_and_a_long_label(
    logged_in_client, jawa_env, monkeypatch, tmp_path
):
    monkeypatch.setattr(ssh, "ICON_DIR", str(tmp_path / "icons"))
    for extra in (
        {"webclip_icon": (_png(64), "icon.png")},
        {"webclip_label": "x" * 21},
    ):
        logged_in_client.post(
            "/automations/tap/new",
            data=_create_form(**extra),
            content_type="multipart/form-data",
        )
        assert data_store.get_webhook_by_name("reset-ipad") is None


def test_edit_can_rotate_the_token(
    logged_in_client, client, jawa_env, profile_jamf
):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    old = data_store.get_webhook_by_name("reset-ipad")["token"]
    form = _create_form(rotate_token="on")
    del form["new_file"]
    logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    new = data_store.get_webhook_by_name("reset-ipad")["token"]
    assert new != old
    query = {"token": old, "id": "7", "udid": "UDID-1"}
    assert client.get("/tap/reset-ipad", query_string=query).status_code == 401
    query["token"] = new
    assert client.get("/tap/reset-ipad", query_string=query).status_code == 200
    _, kwargs = profile_jamf.puts[-1]
    assert new in kwargs["data"]
    assert old not in kwargs["data"]


def test_edit_without_the_box_keeps_the_token(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(),
        content_type="multipart/form-data",
    )
    old = data_store.get_webhook_by_name("reset-ipad")["token"]
    form = _create_form()
    del form["new_file"]
    logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    assert data_store.get_webhook_by_name("reset-ipad")["token"] == old


def test_edit_creates_a_missing_profile(
    logged_in_client, jawa_env, profile_jamf
):
    profile_jamf.status = 400
    logged_in_client.post(
        "/automations/tap/new",
        data=_create_form(create_profile="on"),
        content_type="multipart/form-data",
    )
    assert (
        data_store.get_webhook_by_name("reset-ipad")["profile_status"]
        == "failed"
    )
    page = logged_in_client.get("/automations/tap/reset-ipad/edit").get_data(
        as_text=True
    )
    assert 'name="create_profile"' in page

    profile_jamf.status = 201
    profile_jamf.posts.clear()
    form = _create_form(create_profile="on")
    del form["new_file"]
    logged_in_client.post(
        "/automations/tap/reset-ipad/edit",
        data=dict(form, button_choice="Save"),
        content_type="multipart/form-data",
    )
    assert any(
        "/mobiledeviceconfigurationprofiles/id/0" in url
        for url, _ in profile_jamf.posts
    )
    entry = data_store.get_webhook_by_name("reset-ipad")
    assert entry["jamf_id"] == "55"
    assert entry["profile_status"] == "created"
    page = logged_in_client.get("/automations/tap/reset-ipad/edit").get_data(
        as_text=True
    )
    assert 'name="create_profile"' not in page
