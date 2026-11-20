"""M3-3: the Brander template store.

A package is one JSON file (the .jawa.json idea: no zip, so no zip-slip)
holding a wallrender template and its assets as base64. Packages are
validated with the vendored wallrender, stored as immutable numbered
versions per tenant, and activated with an audit trail. Brander renders
the active version when its template setting is store:<slug>.
"""

import base64
import io
import json
import os

import pytest
from PIL import Image

from bin import brander_store as store

TEMPLATE = {
    "schema_version": 1,
    "name": "Ward iPads",
    "canvas": {"width": 120, "height": 240},
    "background": {"color": "#0B2545"},
    "layers": [
        {
            "type": "image",
            "asset": "logo",
            "box": {"x": 0.25, "y": 0.1, "w": 0.5, "h": 0.25},
        },
    ],
}
TENANT = "https://acme.jamfcloud.com"


def png(color=(200, 0, 0), size=(20, 20), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def package(name="Ward iPads", template=None, assets=None):
    return json.dumps(
        {
            "kind": "brander-template",
            "format": 1,
            "name": name,
            "template": template or TEMPLATE,
            "assets": assets
            if assets is not None
            else {"logo": base64.b64encode(png()).decode()},
        }
    ).encode()


@pytest.fixture(autouse=True)
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


# --- validation ----------------------------------------------------------------


def test_a_good_package_validates():
    pkg, problems = store.validate_package(package())
    assert problems == [] and pkg["name"] == "Ward iPads"


@pytest.mark.parametrize(
    "raw, fragment",
    [
        (b"{nope", "JSON"),
        (b"[]", "object"),
        (
            json.dumps({"kind": "other", "format": 1}).encode(),
            "brander-template",
        ),
        (package(template={"schema_version": 9}), "schema_version"),
        (package(assets={}), "logo"),
        (package(assets={"logo": "not base64!!"}), "logo"),
        (
            package(
                assets={"logo": base64.b64encode(png(fmt="GIF")).decode()}
            ),
            "PNG or JPEG",
        ),
        (
            package(assets={"logo": base64.b64encode(b"GIF89a....").decode()}),
            "readable image",
        ),
        (
            package(
                assets={
                    "logo": base64.b64encode(png()).decode(),
                    "../evil": base64.b64encode(png()).decode(),
                }
            ),
            "asset id",
        ),
        (package(name=""), "name"),
    ],
)
def test_bad_packages_are_refused(raw, fragment):
    pkg, problems = store.validate_package(raw)
    assert pkg is None
    assert any(fragment in p for p in problems), problems


def test_oversized_package_is_refused_before_parsing(monkeypatch):
    monkeypatch.setattr(store, "MAX_PACKAGE_BYTES", 100)
    _, problems = store.validate_package(package())
    assert any("too large" in p for p in problems)


def test_too_many_assets(monkeypatch):
    monkeypatch.setattr(store, "MAX_ASSETS", 1)
    assets = {
        "logo": base64.b64encode(png()).decode(),
        "extra": base64.b64encode(png()).decode(),
    }
    _, problems = store.validate_package(package(assets=assets))
    assert any("at most 1" in p for p in problems)


def test_jpeg_assets_are_accepted():
    assets = {"logo": base64.b64encode(png(fmt="JPEG")).decode()}
    assert store.validate_package(package(assets=assets))[1] == []


# --- versions, activation, audit -------------------------------------------------


def test_upload_creates_v1_active_and_audited(store_dir):
    result = store.save_version(TENANT, package(), "alice", now=1000.0)
    assert result == {
        "slug": "ward-ipads",
        "version": 1,
        "active": True,
        "sha256": result["sha256"],
    }
    [entry] = store.list_templates(TENANT)
    assert entry["slug"] == "ward-ipads" and entry["active"] == 1
    assert entry["versions"][0]["uploaded_by"] == "alice"
    assert entry["activations"] == [
        {"version": 1, "by": "alice", "at": 1000.0}
    ]
    path = store.active_template_path(TENANT, "ward-ipads")
    assert path.endswith(os.path.join("ward-ipads", "v1", "template.json"))
    assert os.path.isfile(os.path.join(os.path.dirname(path), "logo.png"))


def test_a_second_upload_is_v2_and_not_active_until_activated():
    store.save_version(TENANT, package(), "alice", now=1.0)
    v1 = store.active_template_path(TENANT, "ward-ipads")
    before = open(v1, "rb").read()
    result = store.save_version(
        TENANT,
        package(template=dict(TEMPLATE, background={"color": "#FFFFFF"})),
        "bob",
        now=2.0,
    )
    assert result["version"] == 2 and result["active"] is False
    assert store.active_template_path(TENANT, "ward-ipads") == v1
    assert open(v1, "rb").read() == before  # versions are immutable
    store.activate(TENANT, "ward-ipads", 2, "carol", now=3.0)
    assert store.active_template_path(TENANT, "ward-ipads").endswith(
        os.path.join("v2", "template.json")
    )
    [entry] = store.list_templates(TENANT)
    assert entry["activations"][-1] == {"version": 2, "by": "carol", "at": 3.0}


def test_activating_a_missing_version_fails():
    store.save_version(TENANT, package(), "alice", now=1.0)
    with pytest.raises(store.StoreError):
        store.activate(TENANT, "ward-ipads", 9, "alice")
    with pytest.raises(store.StoreError):
        store.activate(TENANT, "nope", 1, "alice")


def test_tenants_are_separate():
    store.save_version(TENANT, package(), "alice")
    assert store.list_templates("https://other.jamfcloud.com") == []
    assert (
        store.active_template_path("https://other.jamfcloud.com", "ward-ipads")
        is None
    )


@pytest.mark.parametrize(
    "url, key",
    [
        ("https://Acme.jamfcloud.com/", "acme.jamfcloud.com"),
        ("https://jamf.example.org:8443", "jamf.example.org-8443"),
        ("", "default"),
    ],
)
def test_tenant_keys(url, key):
    assert store.tenant_key(url) == key


def test_slug_comes_from_the_name_and_cannot_escape(store_dir):
    result = store.save_version(TENANT, package(name="../../Etc Passwd!"), "x")
    assert result["slug"] == "etc-passwd"
    assert os.path.isdir(store_dir / "acme.jamfcloud.com" / "etc-passwd")


def test_invalid_upload_writes_nothing(store_dir):
    with pytest.raises(store.StoreError):
        store.save_version(TENANT, package(assets={}), "x")
    assert not store_dir.exists() or not any(store_dir.rglob("template.json"))


# --- Brander renders store:<slug> ------------------------------------------------

from tests.test_brander_templates import (  # noqa: E402,F401 -- fixtures
    SERVER,
    _fresh_wallrender,
    jamf,
    load_brander,
    run,
)


def brander_on_store(store_dir):
    module = load_brander(template_path="store:Ward iPads")
    module.STORE_DIR = str(store_dir)
    return module


def corner(jamf_fake):
    with Image.open(io.BytesIO(jamf_fake.sent_image())) as img:
        return img.convert("RGB").getpixel((2, 2)), img.convert(
            "RGB"
        ).getpixel((60, 50))


def test_brander_renders_the_active_version_with_its_own_assets(
    jamf,  # noqa: F811
    store_dir,
):
    store.save_version(SERVER, package(), "alice")
    module = brander_on_store(store_dir)
    assert run(module) == 0
    background, logo = corner(jamf)
    assert background == (0x0B, 0x25, 0x45)
    assert logo == (200, 0, 0)  # the logo came from the version's folder


def test_activating_a_version_changes_what_brander_sends(
    jamf,  # noqa: F811
    store_dir,
    capsys,
):
    store.save_version(SERVER, package(), "alice")
    white = dict(TEMPLATE, background={"color": "#FFFFFF"})
    store.save_version(SERVER, package(template=white), "bob")
    module = brander_on_store(store_dir)
    run(module)
    assert corner(jamf)[0] == (0x0B, 0x25, 0x45)
    jamf.commands.clear()
    store.activate(SERVER, "ward-ipads", 2, "carol")
    run(module)
    assert corner(jamf)[0] == (255, 255, 255)
    assert "store:ward-ipads v2, sha256" in capsys.readouterr().out


def test_unknown_stored_template_exits_30(jamf, store_dir):  # noqa: F811
    assert run(brander_on_store(store_dir)) == 30
    assert jamf.commands == []


def test_brander_and_the_store_agree_on_tenant_keys():
    module = load_brander()
    for url in (
        "https://Acme.jamfcloud.com/",
        "https://jamf.example.org:8443",
        "",
        "http://10.0.0.5",
    ):
        assert module.tenant_key(url) == store.tenant_key(url)
