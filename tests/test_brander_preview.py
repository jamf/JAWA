"""M3-5: preview a template on a real device without sending it, and
export the tenant's extension attribute names for EWOK."""

import base64
import io
import json

import pytest
import requests
from PIL import Image

from bin import brander_store as store
from bin import brander_values
from tests.test_brander_store import package
from tests.test_brander_templates import device_record, load_brander

JAMF_URL = "https://jamf.example.test"  # tests/conftest.py JAMF_URL


# --- the console's rules match the deployed script's -------------------------------

ROLE_PERSON_TEMPLATE = {
    "person_fields": True,
    "roles": {"attribute": "Jamf Setup Role"},
}


@pytest.mark.parametrize("template", [None, {}, ROLE_PERSON_TEMPLATE])
@pytest.mark.parametrize("allow", [True, False])
def test_preview_values_match_the_brander_script(template, allow):
    module = load_brander()
    module.ALLOW_PERSON_FIELDS = "yes" if allow else "no"
    record = device_record()
    record["extension_attributes"] = [
        {"name": "Jamf Setup Role", "value": "Nursing"},
        {"name": "Other", "value": "secret"},
    ]
    assert brander_values.build_values(
        record, template, allow
    ) == module.build_values(record, template)


@pytest.mark.parametrize("model", ["iPad8,5", "iPhone15,3", "AppleTV1,1", ""])
def test_set_choice_matches_the_brander_script(model):
    module = load_brander()
    sets = {
        "templates": {
            "iPad8,5": "exact.json",
            "iphone": "phone.json",
            "default": "d.json",
        }
    }
    record = device_record(model_identifier=model)
    expected = {"iPad8,5": "exact.json", "iPhone15,3": "phone.json"}.get(
        model, "d.json"
    )
    assert brander_values.set_entry(sets, record) == expected
    assert module.device_family(model) == brander_values.device_family(model)


# --- the preview page ------------------------------------------------------------


class FakeGet:
    def __init__(self, device=None, status=200, eas=None):
        self.device, self.status, self.eas = device, status, eas
        self.urls = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        resp = requests.Response()
        if url.endswith("/JSSResource/activationcode"):
            resp.status_code = 200
            resp._content = json.dumps(
                {"license_information": {"organization_name": "T"}}
            ).encode()
            return resp
        if "/mobiledeviceextensionattributes" in url:
            resp.status_code = 200
            resp._content = json.dumps(
                {"mobile_device_extension_attributes": self.eas or []}
            ).encode()
            return resp
        resp.status_code = self.status
        resp._content = json.dumps({"mobile_device": self.device}).encode()
        return resp


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


@pytest.fixture()
def no_sends(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError(
            "the preview must never send anything to Jamf Pro"
        )

    monkeypatch.setattr(requests, "put", refuse)
    monkeypatch.setattr(requests, "delete", refuse)
    return refuse


def logged_in_with(monkeypatch, logged_in_client, fake):
    monkeypatch.setattr(requests, "get", fake)
    return logged_in_client


def test_preview_page_needs_a_login(client, jawa_env):
    resp = client.get("/brander/preview")
    assert resp.status_code == 302


def test_preview_page_lists_stored_and_shipped_templates(
    logged_in_client, jawa_env, store_dir
):
    store.save_version(JAMF_URL, package(), "pytest-admin")
    body = logged_in_client.get("/brander/preview").get_data(as_text=True)
    assert '<option value="store:ward-ipads"' in body
    assert '<option value="example-ipad-template.json"' in body
    assert "Nothing is sent" in body


def test_preview_renders_a_stored_template_for_a_real_device(
    logged_in_client, jawa_env, store_dir, monkeypatch, no_sends
):
    store.save_version(JAMF_URL, package(), "pytest-admin")
    fake = FakeGet(device=device_record())
    client = logged_in_with(monkeypatch, logged_in_client, fake)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no POST")),
    )
    resp = client.post(
        "/brander/preview",
        data={"template": "store:ward-ipads", "jss_id": "42"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert any(
        u.endswith("/JSSResource/mobiledevices/id/42") for u in fake.urls
    )
    data = body.split('src="data:image/png;base64,', 1)[1].split('"', 1)[0]
    with Image.open(io.BytesIO(base64.b64decode(data))) as img:
        assert img.size == (120, 240)
    assert "Ward 3 iPad" in body  # the record it used
    assert "Nothing was sent" in body


def test_preview_of_an_unknown_device_says_so(
    logged_in_client, jawa_env, store_dir, monkeypatch, no_sends
):
    store.save_version(JAMF_URL, package(), "pytest-admin")
    client = logged_in_with(monkeypatch, logged_in_client, FakeGet(status=404))
    resp = client.post(
        "/brander/preview",
        data={"template": "store:ward-ipads", "jss_id": "9"},
    )
    assert resp.status_code == 404
    assert "No mobile device with Jamf ID 9" in resp.get_data(as_text=True)


@pytest.mark.parametrize("jss_id", ["abc", "", "-1"])
def test_preview_needs_a_numeric_id(
    logged_in_client, jawa_env, store_dir, jss_id
):
    resp = logged_in_client.post(
        "/brander/preview", data={"template": "legacy.json", "jss_id": jss_id}
    )
    assert resp.status_code == 400


def test_preview_refuses_templates_outside_the_list(
    logged_in_client, jawa_env, store_dir, monkeypatch, no_sends
):
    client = logged_in_with(
        monkeypatch, logged_in_client, FakeGet(device=device_record())
    )
    resp = client.post(
        "/brander/preview",
        data={"template": "../../etc/passwd", "jss_id": "42"},
    )
    assert resp.status_code == 400


def test_preview_of_a_template_set_uses_the_devices_model(
    logged_in_client, jawa_env, store_dir, monkeypatch, no_sends
):
    client = logged_in_with(
        monkeypatch,
        logged_in_client,
        FakeGet(device=device_record(model_identifier="iPhone15,3")),
    )
    body = client.post(
        "/brander/preview",
        data={"template": "example-set.json", "jss_id": "42"},
    ).get_data(as_text=True)
    assert "example-template.json" in body


# --- extension attribute names for EWOK ------------------------------------------


def test_ea_names_export_is_names_only(
    logged_in_client, jawa_env, monkeypatch, no_sends
):
    eas = [{"id": 1, "name": "Jamf Setup Role"}, {"id": 2, "name": "Brander"}]
    client = logged_in_with(monkeypatch, logged_in_client, FakeGet(eas=eas))
    resp = client.get("/brander/ea-names.json")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert json.loads(resp.data) == {
        "kind": "jamf-ea-names",
        "format": 1,
        "names": ["Brander", "Jamf Setup Role"],
    }
