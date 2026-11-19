"""Milestone 4: a template's screen choice wins over the Brander setting,
and the console preview checks fit on the device's family of screens."""

import re

import pytest

from tests.test_brander_templates import (  # noqa: F401 -- fixtures
    _fresh_wallrender,
    basic_template,
    jamf,
    load_brander,
    run,
    write_template,
)


def sent_setting(fake):
    return int(
        re.search(
            r"<wallpaper_setting>(\d)</wallpaper_setting>", fake.commands[0]
        ).group(1)
    )


@pytest.mark.parametrize(
    "screen, expected", [("lock", 1), ("home", 2), ("both", 3), (None, 3)]
)
def test_template_screen_picks_the_wallpaper_target(
    jamf,  # noqa: F811
    tmp_path,
    screen,
    expected,
):
    template = basic_template()
    if screen:
        template["screen"] = screen
    module = load_brander(
        template_path=write_template(tmp_path, template)
    )  # setting is 3
    assert run(module) == 0
    assert sent_setting(jamf) == expected


def test_legacy_layout_keeps_the_brander_setting(jamf):  # noqa: F811
    module = load_brander()
    module.WALLPAPER_SETTING = 1
    assert run(module) == 0
    assert sent_setting(jamf) == 1


def test_preview_reports_fit_on_the_devices_family(
    logged_in_client, jawa_env, tmp_path, monkeypatch
):
    from bin import brander_store as store
    from tests.test_brander_preview import FakeGet
    from tests.test_brander_store import package
    from tests.test_brander_templates import device_record
    import requests

    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    store.save_version("https://jamf.example.test", package(), "pytest-admin")
    monkeypatch.setattr(
        requests,
        "get",
        FakeGet(device=device_record(model_identifier="iPhone17,1")),
    )
    body = logged_in_client.post(
        "/brander/preview",
        data={"template": "store:ward-ipads", "jss_id": "42"},
    ).get_data(as_text=True)
    assert "Fit on lock screens" in body
    assert (
        "iPhone 6.7-inch" in body
        and "iPad Pro" not in body.split("Checked on:")[1].split("</p>")[0]
    )
    assert (
        "under the Clock" in body
    )  # the logo sits at the top of an iPhone lock screen
