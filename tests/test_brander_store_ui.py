"""M3-4: the Brander template store in the console, and the Brander
enable form's template suggestions."""

import io

import pytest

from bin import brander_store as store
from tests.test_brander_store import TEMPLATE, package

JAMF_URL = "https://jamf.example.test"  # tests/conftest.py JAMF_URL


@pytest.fixture(autouse=True)
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


def upload(client, raw, name="ward.brander.json"):
    return client.post(
        "/brander/templates",
        data={"package": (io.BytesIO(raw), name)},
        content_type="multipart/form-data",
    )


def test_the_page_needs_a_login(client, jawa_env):
    resp = client.get("/brander/templates")
    assert (
        resp.status_code == 302 and "log" in resp.headers["Location"]
    )  # to sign-in
    assert upload(client, package()).status_code == 302
    assert store.list_templates(JAMF_URL) == []


def test_empty_store_explains_what_to_do(logged_in_client, jawa_env):
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert "No templates yet" in body
    assert ".brander.json" in body


def test_upload_stores_v1_for_the_logged_in_tenant(logged_in_client, jawa_env):
    resp = upload(logged_in_client, package())
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Uploaded Ward iPads as version 1" in body
    assert "store:ward-ipads" in body
    [entry] = store.list_templates(JAMF_URL)
    assert entry["versions"][0]["uploaded_by"] == "pytest-admin"


def test_a_bad_upload_lists_its_problems_and_stores_nothing(
    logged_in_client, jawa_env
):
    resp = upload(logged_in_client, package(assets={}))
    assert resp.status_code == 400
    assert "logo" in resp.get_data(as_text=True)
    assert store.list_templates(JAMF_URL) == []


def test_upload_without_a_file_is_400(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/brander/templates", data={}, content_type="multipart/form-data"
    )
    assert resp.status_code == 400


def test_activate_switches_versions_and_audits(logged_in_client, jawa_env):
    upload(logged_in_client, package())
    upload(
        logged_in_client,
        package(template=dict(TEMPLATE, background={"color": "#FFFFFF"})),
    )
    resp = logged_in_client.post(
        "/brander/templates/ward-ipads/activate", data={"version": "2"}
    )
    assert resp.status_code == 302
    [entry] = store.list_templates(JAMF_URL)
    assert entry["active"] == 2
    assert entry["activations"][-1]["by"] == "pytest-admin"
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert "Version 2" in body and "active" in body.lower()


@pytest.mark.parametrize("version", ["9", "abc", ""])
def test_activating_a_bad_version_is_refused(
    logged_in_client, jawa_env, version
):
    upload(logged_in_client, package())
    resp = logged_in_client.post(
        "/brander/templates/ward-ipads/activate", data={"version": version}
    )
    assert resp.status_code == 400
    assert store.list_templates(JAMF_URL)[0]["active"] == 1


def test_extras_menu_links_the_store(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").get_data(as_text=True)
    assert 'href="/brander/templates"' in body


def test_enable_form_suggests_stored_and_shipped_templates(
    logged_in_client, jawa_env
):
    upload(logged_in_client, package())
    body = logged_in_client.get("/templates/tap-brander/enable").get_data(
        as_text=True
    )
    assert 'list="templatePathOptions"' in body
    for option in (
        "legacy",
        "store:ward-ipads",
        "example-set.json",
        "example-template.json",
    ):
        assert f'<option value="{option}"' in body


def test_store_page_says_which_branders_use_each_template(
    logged_in_client, jawa_env, tmp_path
):
    from tests.test_brander_settings import _service, deployed

    upload(logged_in_client, package())
    _service(
        jawa_env,
        deployed(
            tmp_path, **{'"__JAWA_TEMPLATE_PATH__"': repr("store:ward-ipads")}
        ),
    )
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert "Used by: brand-device" in body


def test_store_page_says_when_nothing_uses_a_template(
    logged_in_client, jawa_env
):
    upload(logged_in_client, package())
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert "Not used by any Brander yet" in body
    assert "store:ward-ipads" in body
