"""Store sets: one Brander, a stored template per kind of device.

A template setting of store:iphone=<name> ipad=<name> picks a stored
template by model identifier, family, then default, the same keys as a
template set file. The store page shows how each active version and each
upload fits every iPhone and iPad screen.
"""

import io

import pytest
from PIL import Image

from bin import brander_settings as bs
from bin import brander_store as store
from tests.test_brander_settings import _service, deployed
from tests.test_brander_store import TEMPLATE, package
from tests.test_brander_templates import (  # noqa: F401 -- fixtures
    SERVER,
    _fresh_wallrender,
    jamf,
    load_brander,
    run,
)

JAMF_URL = "https://jamf.example.test"  # tests/conftest.py JAMF_URL

PHONE = dict(
    TEMPLATE,
    name="Front desk",
    canvas={"width": 129, "height": 280},
    background={"color": "#FFFFFF"},
)
PAD = dict(
    TEMPLATE,
    name="Ward iPads",
    canvas={"width": 200, "height": 200},
    background={"color": "#0B2545"},
)


@pytest.fixture(autouse=True)
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


# --- parsing ---------------------------------------------------------------


def test_one_name_is_not_a_set():
    assert store.store_set("ward-ipads") is None
    assert store.store_slugs("store:Ward iPads") == ["ward-ipads"]


def test_a_set_maps_keys_to_slugs():
    entries = store.store_set(
        " iphone=Front-Desk ipad=ward-ipads iPad8,5=pro default=front-desk "
    )
    assert entries == {
        "iphone": "front-desk",
        "ipad": "ward-ipads",
        "iPad8,5": "pro",
        "default": "front-desk",
    }
    assert store.store_slugs(
        "store:iphone=front-desk ipad=ward-ipads default=front-desk"
    ) == ["front-desk", "ward-ipads"]


@pytest.mark.parametrize(
    "spec",
    ["iphone=a ipad", "=a", "iphone=", "iphone=a iphone=b", "iphone=!!!"],
)
def test_malformed_sets_are_refused(spec):
    with pytest.raises(store.StoreError):
        store.store_set(spec)
    assert store.store_slugs("store:" + spec) == []


@pytest.mark.parametrize(
    "model, expected",
    [
        ("iPad8,5", "pro"),
        ("iPad13,1", "wards"),
        ("iPhone15,3", "desk"),
        ("AppleTV11,1", "desk"),
        ("", "desk"),
    ],
)
def test_console_and_script_pick_the_same_template(model, expected):
    spec = "iphone=desk ipad=wards iPad8,5=pro default=desk"
    module = load_brander(template_path="legacy")
    device = {"general": {"model_identifier": model}}
    assert store.set_choice(store.store_set(spec), model) == expected
    assert module.store_pick(spec, device) == expected


def test_a_set_without_a_match_or_default_picks_nothing():
    assert store.set_choice({"ipad": "wards"}, "iPhone15,3") is None


# --- the Brander script ------------------------------------------------------


def brander_with(store_dir, setting):
    module = load_brander(template_path=setting)
    module.STORE_DIR = str(store_dir)
    return module


@pytest.mark.parametrize(
    "model, size", [("iPhone15,3", (129, 280)), ("iPad8,5", (200, 200))]
)
def test_brander_sends_each_family_its_own_stored_template(
    jamf,  # noqa: F811
    store_dir,
    model,
    size,
):
    store.save_version(
        SERVER, package(name="Front desk", template=PHONE), "alice"
    )
    store.save_version(
        SERVER, package(name="Ward iPads", template=PAD), "alice"
    )
    jamf.device["general"]["model_identifier"] = model
    assert (
        run(brander_with(store_dir, "store:iphone=front-desk ipad=ward-ipads"))
        == 0
    )
    with Image.open(io.BytesIO(jamf.sent_image())) as img:
        assert img.size == size


def test_brander_exits_30_when_the_set_has_nothing_for_the_device(
    jamf,  # noqa: F811
    store_dir,
    capsys,
):
    store.save_version(
        SERVER, package(name="Ward iPads", template=PAD), "alice"
    )
    jamf.device["general"]["model_identifier"] = "iPhone15,3"
    assert run(brander_with(store_dir, "store:ipad=ward-ipads")) == 30
    assert jamf.commands == []
    assert "no template for iPhone15,3" in capsys.readouterr().out


def test_brander_exits_30_on_a_malformed_set(jamf, store_dir):  # noqa: F811
    assert run(brander_with(store_dir, "store:iphone=a ipad")) == 30
    assert jamf.commands == []


# --- settings ------------------------------------------------------------------


def test_settings_accept_a_store_set(tmp_path):
    path = deployed(tmp_path)
    bs.write_settings(
        path, {"template_path": "store:iphone=front-desk ipad=ward-ipads"}
    )
    assert (
        bs.read_settings(path)["template_path"]
        == "store:iphone=front-desk ipad=ward-ipads"
    )


def test_settings_refuse_a_malformed_store_set(tmp_path):
    path = deployed(tmp_path)
    with pytest.raises(bs.SettingsError) as err:
        bs.write_settings(
            path, {"template_path": "store:iphone=front-desk ipad"}
        )
    assert "Store set" in err.value.problems[0]
    assert bs.read_settings(path)["template_path"] == "legacy"


# --- the console ---------------------------------------------------------------


def upload(client, raw):
    return client.post(
        "/brander/templates",
        data={"package": (io.BytesIO(raw), "t.brander.json")},
        content_type="multipart/form-data",
    )


def test_store_page_counts_a_set_as_using_each_template(
    logged_in_client, jawa_env, tmp_path
):
    upload(logged_in_client, package(name="Front desk", template=PHONE))
    upload(logged_in_client, package(name="Ward iPads", template=PAD))
    _service(
        jawa_env,
        deployed(
            tmp_path,
            **{
                '"__JAWA_TEMPLATE_PATH__"': repr(
                    "store:iphone=front-desk ipad=ward-ipads"
                )
            },
        ),
    )
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert body.count("Used by: brand-device") == 2
    assert "A template per kind of device" in body


def test_store_page_shows_how_the_active_version_fits(
    logged_in_client, jawa_env
):
    # A tall iPhone layout with a layer near the bottom: iPads crop it off.
    tall = dict(
        PHONE,
        layers=[
            {
                "type": "qr",
                "data": "x",
                "box": {"x": 0.35, "y": 0.72, "w": 0.3, "h": 0.14},
            }
        ],
    )
    resp = upload(logged_in_client, package(name="Front desk", template=tall))
    body = resp.get_data(as_text=True)
    assert "iPad: check the layout." in body
    assert (
        "Layer 1 (QR code): cut off on iPad Pro 12.9-inch (landscape)" in body
    )
    page = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert "How the active version fits:" in page
    assert "iPad: check the layout." in page


def test_a_centred_square_fits_every_ipad(logged_in_client, jawa_env):
    square = dict(
        PAD,
        layers=[
            {
                "type": "qr",
                "data": "x",
                "box": {"x": 0.4, "y": 0.45, "w": 0.2, "h": 0.2},
            }
        ],
    )
    body = upload(
        logged_in_client, package(name="Ward iPads", template=square)
    ).get_data(as_text=True)
    assert "iPad: fits" in body


def test_preview_lists_and_resolves_a_store_set(
    logged_in_client, jawa_env, tmp_path, monkeypatch
):
    import requests

    from tests.test_brander_preview import FakeGet, device_record

    store.save_version(
        JAMF_URL, package(name="Front desk", template=PHONE), "pytest-admin"
    )
    store.save_version(
        JAMF_URL, package(name="Ward iPads", template=PAD), "pytest-admin"
    )
    setting = "store:iphone=front-desk ipad=ward-ipads"
    _service(
        jawa_env,
        deployed(tmp_path, **{'"__JAWA_TEMPLATE_PATH__"': repr(setting)}),
    )
    assert f'<option value="{setting}"' in logged_in_client.get(
        "/brander/preview"
    ).get_data(as_text=True)

    monkeypatch.setattr(
        requests,
        "get",
        FakeGet(device=device_record(model_identifier="iPad8,5")),
    )
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no POST")),
    )
    body = logged_in_client.post(
        "/brander/preview", data={"template": setting, "jss_id": "42"}
    ).get_data(as_text=True)
    assert "picked store:ward-ipads" in body


# --- wallrender 0.9.0: panel layers ---------------------------------------------


def test_brander_renders_a_stored_template_with_a_panel(jamf, store_dir):  # noqa: F811
    panelled = dict(
        PHONE,
        layers=[
            {
                "type": "panel",
                "color": "#000000",
                "opacity": 1,
                "box": {"x": 0, "y": 0, "w": 1, "h": 0.5},
            }
        ],
    )
    store.save_version(
        SERVER,
        package(name="Front desk", template=panelled, assets={}),
        "alice",
    )
    assert run(brander_with(store_dir, "store:front-desk")) == 0
    with Image.open(io.BytesIO(jamf.sent_image())) as img:
        rgb = img.convert("RGB")
        assert rgb.getpixel((60, 20)) == (0, 0, 0)  # under the panel
        assert rgb.getpixel((60, 260)) == (
            255,
            255,
            255,
        )  # the white background


def test_fit_summary_names_panel_layers():
    panelled = dict(
        PHONE,
        layers=[
            {"type": "panel", "box": {"x": 0, "y": 0.9, "w": 1, "h": 0.1}}
        ],
    )
    ipad = [f for f in store.fit_summary(panelled) if f["family"] == "iPad"][0]
    assert any(w.startswith("Layer 1 (panel):") for w in ipad["warnings"])
