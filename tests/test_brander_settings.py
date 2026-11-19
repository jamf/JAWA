"""M3-5: change an enabled Brander's settings, and update its script,
without re-enabling it (which would mint a new web clip)."""

import os
import re

import pytest

from bin import brander_settings as bs

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(
    REPO_ROOT, "data", "workflows", "scripts", "tap_brander.py"
)


def deployed(tmp_path, **overrides):
    """A Brander script as enabling it writes one: every token filled."""
    values = {
        '"__JAWA_SERVER_URL__"': repr("https://acme.jamfcloud.com"),
        '"__JAWA_CLIENT_ID__"': repr("client-id"),
        '"__JAWA_CLIENT_SECRET__"': repr("s3cret"),
        "__JAWA_EA_ID__": "0",
        "__JAWA_WALLPAPER_SETTING__": "3",
        '"__JAWA_ASSETS_DIR__"': repr("/srv/assets"),
        '"__JAWA_FONT_PATH__"': repr("none"),
        '"__JAWA_TEMPLATE_PATH__"': repr("legacy"),
        "__JAWA_MAX_KB__": "1500",
        '"__JAWA_ALLOW_PERSON_FIELDS__"': repr("no"),
    }
    values.update(overrides)
    source = open(SOURCE).read()
    for token, value in values.items():
        source = source.replace(token, value)
    source = "#!/opt/jawa/venv/bin/python3\n" + source.split("\n", 1)[1]
    path = tmp_path / "brand-device.py"
    path.write_text(source)
    return str(path)


def test_a_brander_script_is_recognised(tmp_path):
    assert bs.is_brander_script(deployed(tmp_path))
    other = tmp_path / "other.py"
    other.write_text("print('hi')\n")
    assert not bs.is_brander_script(str(other))
    assert not bs.is_brander_script(str(tmp_path / "missing.py"))


def test_read_settings(tmp_path):
    assert bs.read_settings(deployed(tmp_path)) == {
        "template_path": "legacy",
        "max_kb": 1500,
        "allow_person_fields": "no",
        "wallpaper_setting": 3,
    }


def test_read_settings_never_returns_credentials(tmp_path):
    settings = bs.read_settings(deployed(tmp_path))
    assert "s3cret" not in repr(settings) and "client-id" not in repr(settings)


def test_write_settings_changes_only_those_lines(tmp_path):
    path = deployed(tmp_path)
    before = open(path).read().splitlines()
    bs.write_settings(
        path,
        {
            "template_path": "store:ward-ipads",
            "max_kb": "900",
            "allow_person_fields": "yes",
            "wallpaper_setting": "1",
        },
    )
    after = open(path).read().splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(changed) == 4 and len(before) == len(after)
    assert bs.read_settings(path) == {
        "template_path": "store:ward-ipads",
        "max_kb": 900,
        "allow_person_fields": "yes",
        "wallpaper_setting": 1,
    }
    compile(open(path).read(), path, "exec")


@pytest.mark.parametrize(
    "updates, fragment",
    [
        ({"template_path": ""}, "template"),
        ({"template_path": "a\nimport os"}, "template"),
        ({"template_path": "x" * 301}, "template"),
        ({"max_kb": "abc"}, "size"),
        ({"max_kb": "10"}, "size"),
        ({"allow_person_fields": "maybe"}, "yes or no"),
        ({"wallpaper_setting": "4"}, "1, 2 or 3"),
    ],
)
def test_bad_settings_are_refused_and_nothing_is_written(
    tmp_path, updates, fragment
):
    path = deployed(tmp_path)
    before = open(path).read()
    with pytest.raises(bs.SettingsError) as err:
        bs.write_settings(path, updates)
    assert any(fragment in p for p in err.value.problems)
    assert open(path).read() == before


def test_a_quote_in_the_template_path_stays_a_string(tmp_path):
    path = deployed(tmp_path)
    bs.write_settings(path, {"template_path": "it's.json"})
    assert bs.read_settings(path)["template_path"] == "it's.json"
    compile(open(path).read(), path, "exec")


def test_refresh_keeps_settings_credentials_and_shebang(tmp_path):
    path = deployed(tmp_path, **{'"__JAWA_TEMPLATE_PATH__"': repr("store:x")})
    with open(path) as handle:
        text = handle.read()
    # Pretend it was enabled from an older Brander without newer settings.
    old = re.sub(r"^ALLOW_PERSON_FIELDS = .*\n", "", text, flags=re.M).replace(
        "def preflight", "def _old_preflight"
    )
    open(path, "w").write(old)
    bs.refresh_script(path, SOURCE)
    refreshed = open(path).read()
    assert refreshed.startswith("#!/opt/jawa/venv/bin/python3\n")
    assert "s3cret" in refreshed and "client-id" in refreshed
    assert "def preflight" in refreshed  # the current code
    assert bs.read_settings(path) == {
        "template_path": "store:x",
        "max_kb": 1500,
        "allow_person_fields": "no",
        "wallpaper_setting": 3,
    }
    assert "__JAWA_" not in refreshed
    compile(refreshed, path, "exec")


def test_refresh_refuses_a_script_that_is_not_brander(tmp_path):
    other = tmp_path / "other.py"
    other.write_text("print('hi')\n")
    with pytest.raises(bs.SettingsError):
        bs.refresh_script(str(other), SOURCE)


# --- the edit form -----------------------------------------------------------------


def _service(jawa_env, script_path):
    entry = {
        "name": "brand-device",
        "tag": "tap",
        "url": "https://jamf.example.test",
        "jawa_admin": "pytest-admin",
        "script": script_path,
        "description": "",
        "token": "t",
        "device_family": "mobile",
        "cooldown_minutes": 5,
        "page_title": "Brand {DEVICENAME}",
        "page_description": "Apply the wallpaper.",
        "confirm_label": "Apply",
        "success_message": "Done.",
        "failure_message": "Failed.",
        "jamf_id": None,
        "profile_status": "skipped",
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }
    jawa_env.add_webhook(entry)
    return entry


def _form(entry, **brander):
    form = {
        k: entry[k]
        for k in (
            "page_title",
            "page_description",
            "confirm_label",
            "success_message",
            "failure_message",
            "device_family",
        )
    }
    form["cooldown_minutes"] = "5"
    form.update({f"brander_{k}": v for k, v in brander.items()})
    return form


def test_edit_page_shows_brander_settings_but_no_secrets(
    logged_in_client, jawa_env, tmp_path
):
    _service(jawa_env, deployed(tmp_path))
    body = logged_in_client.get("/automations/tap/brand-device/edit").get_data(
        as_text=True
    )
    assert 'name="brander_template_path"' in body and 'value="legacy"' in body
    assert 'name="brander_refresh"' in body
    assert "s3cret" not in body and "client-id" not in body


def test_edit_page_has_no_brander_section_for_other_scripts(
    logged_in_client, jawa_env, tmp_path
):
    other = tmp_path / "rts.py"
    other.write_text("print('rts')\n")
    _service(jawa_env, str(other))
    body = logged_in_client.get("/automations/tap/brand-device/edit").get_data(
        as_text=True
    )
    assert "brander_template_path" not in body


def test_saving_the_edit_form_changes_the_settings(
    logged_in_client, jawa_env, tmp_path
):
    path = deployed(tmp_path)
    entry = _service(jawa_env, path)
    resp = logged_in_client.post(
        "/automations/tap/brand-device/edit",
        data=_form(
            entry,
            template_path="store:ward-ipads",
            max_kb="800",
            wallpaper_setting="1",
            allow_person_fields="yes",
        ),
    )
    assert resp.status_code in (200, 302)
    assert bs.read_settings(path) == {
        "template_path": "store:ward-ipads",
        "max_kb": 800,
        "allow_person_fields": "yes",
        "wallpaper_setting": 1,
    }


def test_a_bad_setting_shows_an_error_and_changes_nothing(
    logged_in_client, jawa_env, tmp_path
):
    path = deployed(tmp_path)
    entry = _service(jawa_env, path)
    before = open(path).read()
    resp = logged_in_client.post(
        "/automations/tap/brand-device/edit",
        data=_form(
            entry,
            template_path="ok.json",
            max_kb="5",
            wallpaper_setting="3",
            allow_person_fields="no",
        ),
    )
    assert "KB" in resp.get_data(as_text=True) or resp.status_code in (
        302,
        400,
    )
    assert open(path).read() == before


def test_refresh_from_the_edit_form(logged_in_client, jawa_env, tmp_path):
    path = deployed(tmp_path)
    text = open(path).read().replace("def preflight", "def _old_preflight")
    open(path, "w").write(text)
    entry = _service(jawa_env, path)
    logged_in_client.post(
        "/automations/tap/brand-device/edit",
        data=dict(
            _form(
                entry,
                template_path="legacy",
                max_kb="1500",
                wallpaper_setting="3",
                allow_person_fields="no",
            ),
            brander_refresh="on",
        ),
    )
    assert "def preflight" in open(path).read()
