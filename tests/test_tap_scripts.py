"""Both Tap Action script templates refuse to act on a UDID mismatch.

Return to Service and Brander are triggered from the device itself
via a caller-supplied Jamf Pro id; the id alone must never be enough
to touch the device (ADR-0012) -- fetch_verified_device() must refuse
unless the UDID Jamf Pro has on file for that id matches the caller's
own UDID. Lock that in for both templates, with no network: the stub
replaces the only network call fetch_verified_device() makes.
"""

import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "data", "workflows", "scripts")


def _load_module(basename):
    """exec() the script's source into a fresh module namespace, the
    same technique as test_brander_script_generates_an_image_without_
    a_font_file in tests/test_tap_templates.py. The bare numeric
    template tokens must become literals for the module to exec at
    all; __JAWA_WALLPAPER_SETTING__, __JAWA_EA_ID__ and __JAWA_MAX_KB__
    are only present in Brander, so the replace is a no-op for RTS.
    """
    path = os.path.join(SCRIPTS_DIR, basename)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source = (
        source.replace("__JAWA_EA_ID__", "0")
        .replace("__JAWA_WALLPAPER_SETTING__", "3")
        .replace("__JAWA_MAX_KB__", "1500")
        .replace('"__JAWA_ALLOW_PERSON_FIELDS__"', '"no"')
    )
    spec = importlib.util.spec_from_loader(basename, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, path, "exec"), module.__dict__)
    return module


@pytest.fixture()
def rts_module():
    module = _load_module("tap_return_to_service.py")
    module.perform_api_call = lambda *a, **k: {
        "udid": "REAL-UDID",
        "managementId": "m",
    }
    return module


@pytest.fixture()
def brander_module():
    module = _load_module("tap_brander.py")
    module.perform_api_call = lambda *a, **k: {
        "mobile_device": {"general": {"udid": "REAL-UDID"}}
    }
    return module


def test_rts_refuses_a_udid_that_does_not_match(rts_module):
    with pytest.raises(SystemExit) as excinfo:
        rts_module.fetch_verified_device(42, "OTHER-UDID")
    assert excinfo.value.code == 20


def test_rts_accepts_a_matching_udid_case_insensitively(rts_module):
    device = rts_module.fetch_verified_device(42, "real-udid")
    assert device == {"udid": "REAL-UDID", "managementId": "m"}


def test_brander_refuses_a_udid_that_does_not_match(brander_module):
    with pytest.raises(SystemExit) as excinfo:
        brander_module.fetch_verified_device(42, "OTHER-UDID")
    assert excinfo.value.code == 20


def test_brander_accepts_a_matching_udid_case_insensitively(
    brander_module,
):
    device = brander_module.fetch_verified_device(42, "real-udid")
    assert device == {"general": {"udid": "REAL-UDID"}}


def test_rts_fetches_the_named_wifi_profile_from_jamf(rts_module):
    """Return to Service reuses a Wi-Fi configuration profile that
    already exists in Jamf Pro (looked up by name), so the payload the
    device receives is one Jamf built -- nothing is typed by hand."""
    seen = {}

    def fake_api(endpoint, method="GET", data=None, api="classic"):
        seen["endpoint"] = endpoint
        return {
            "configuration_profile": {
                "general": {
                    "payloads": (
                        '<?xml version="1.0" encoding="UTF-8"?><plist version="1">'
                        "<dict><key>PayloadContent</key><array><dict>"
                        "<key>PayloadType</key><string>com.apple.wifi.managed</string>"
                        "</dict></array></dict></plist>"
                    )
                }
            }
        }

    rts_module.perform_api_call = fake_api
    plist = rts_module.fetch_wifi_profile_plist("Managed WiFi - MCP")
    assert seen["endpoint"] == (
        "mobiledeviceconfigurationprofiles/name/Managed%20WiFi%20-%20MCP"
    )
    assert b"com.apple.wifi.managed" in plist


def test_rts_refuses_a_profile_that_is_not_wifi(rts_module):
    rts_module.perform_api_call = lambda *a, **k: {
        "configuration_profile": {
            "general": {
                "payloads": (
                    "<plist><dict><key>PayloadType</key>"
                    "<string>com.apple.webClip.managed</string></dict></plist>"
                )
            }
        }
    }
    with pytest.raises(SystemExit) as excinfo:
        rts_module.fetch_wifi_profile_plist("Web Clip")
    assert excinfo.value.code == 25


def test_rts_exits_when_the_wifi_profile_is_missing(rts_module):
    import requests

    def not_found(*a, **k):
        resp = requests.Response()
        resp.status_code = 404
        raise requests.HTTPError(response=resp)

    rts_module.perform_api_call = not_found
    with pytest.raises(SystemExit) as excinfo:
        rts_module.fetch_wifi_profile_plist("Nope")
    assert excinfo.value.code == 24


# --- find_role must never leave the Brander assets directory ------------------
# The role comes from a Jamf extension attribute that the device side can set
# (Jamf Setup), so it is untrusted: "../x" or an absolute path used to select
# any .png on the JAWA host as the wallpaper background.


@pytest.fixture()
def role_assets(tmp_path, brander_module):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in (
        "lockscreen-template",
        "null",
        "videoconferencing",
        "nursing",
    ):
        (assets / f"{name}.png").write_bytes(b"png")
    (tmp_path / "secret.png").write_bytes(b"outside the assets dir")
    brander_module.ASSETS_DIR = str(assets)
    brander_module.EA_ID = 7
    return brander_module, tmp_path


def _device(role):
    return {
        "extension_attributes": [
            {"id": 7, "name": "Setup Role", "value": role}
        ]
    }


@pytest.mark.parametrize(
    "role",
    [
        "../secret",
        "..",
        "../../secret",
        "..%2fsecret",
        "/tmp/secret",
        "nursing/../../secret",
        "x" * 65,
        "Nürsing",
    ],
)
def test_brander_role_cannot_escape_the_assets_directory(role_assets, role):
    module, _ = role_assets
    basename, _label = module.find_role(_device(role))
    assert basename == "lockscreen-template"


def test_brander_role_symlink_out_of_assets_is_refused(role_assets):
    module, tmp_path = role_assets
    os.symlink(
        tmp_path / "secret.png", os.path.join(module.ASSETS_DIR, "evil.png")
    )
    basename, _label = module.find_role(_device("evil"))
    assert basename == "lockscreen-template"


@pytest.mark.parametrize(
    "role,expected",
    [
        ("Video Conferencing", "videoconferencing"),
        ("NURSING", "nursing"),
        ("Pharmacist", "lockscreen-template"),  # no image shipped for it
        ("", "null"),
    ],
)
def test_brander_real_roles_still_match(role_assets, role, expected):
    module, _ = role_assets
    assert module.find_role(_device(role))[0] == expected
