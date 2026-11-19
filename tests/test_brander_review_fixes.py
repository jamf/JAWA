"""JAWA fixes from the 2026-10-02 wrap-up review of Brander."""

import json

import pytest
import requests

from bin import brander_store as store
from bin import data_store
from tests.test_brander_store import TEMPLATE, package
from tests.test_brander_templates import (  # noqa: F401 -- fixtures
    _fresh_wallrender,
    device_record,
    jamf,
    load_brander,
    run,
    write_template,
)

JAMF_URL = "https://jamf.example.test"


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


# --- store versioning survives a lost or corrupt index ----------------------------


@pytest.mark.parametrize("damage", ["delete", "corrupt"])
def test_uploads_continue_after_the_index_is_lost(store_dir, damage):
    store.save_version(JAMF_URL, package(), "alice", now=1.0)
    store.save_version(JAMF_URL, package(), "alice", now=2.0)
    index = store_dir / "jamf.example.test" / "ward-ipads" / "index.json"
    if damage == "delete":
        index.unlink()
    else:
        index.write_text("{nope")
    result = store.save_version(JAMF_URL, package(), "bob", now=3.0)
    assert result["version"] == 3
    [entry] = store.list_templates(JAMF_URL)
    assert [v["version"] for v in entry["versions"]] == [1, 2, 3]
    assert entry["active"] in (1, 2, 3)


# --- crafted templates are problems, not crashes ------------------------------------


def test_a_crafted_screen_value_is_refused_not_a_crash(store_dir):
    pkg, problems = store.validate_package(
        package(template=dict(TEMPLATE, screen=["x"]))
    )
    assert pkg is None and any("screen" in p for p in problems)


def test_the_script_exits_30_on_a_crafted_template(jamf, tmp_path):  # noqa: F811
    path = write_template(tmp_path, dict(TEMPLATE, screen={"a": 1}))
    assert run(load_brander(template_path=path)) == 30


# --- tenant keys ignore default ports ----------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://x.jamfcloud.com",
        "https://x.jamfcloud.com:443/",
        "HTTPS://X.jamfcloud.com",
    ],
)
def test_default_ports_do_not_change_the_tenant(url):
    assert store.tenant_key(url) == "x.jamfcloud.com"
    assert load_brander().tenant_key(url) == "x.jamfcloud.com"


def test_other_ports_still_separate_tenants():
    assert store.tenant_key("https://x.example:8443") == "x.example-8443"
    assert store.tenant_key("http://x.example:80") == "x.example"


# --- the script survives Jamf network failures ----------------------------------------


def test_network_failure_on_lookup_exits_22(jamf, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(requests, "request", boom)
    assert run(load_brander()) == 22


def test_non_json_lookup_exits_22(jamf, monkeypatch):  # noqa: F811
    class NotJson:
        status_code = 200
        text = "<html>maintenance</html>"

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(requests, "request", lambda *a, **k: NotJson())
    assert run(load_brander()) == 22


def test_network_failure_on_send_exits_24(jamf, monkeypatch):  # noqa: F811
    real_post = requests.post

    def post(url, **kw):
        if url.endswith("/Wallpaper"):
            raise requests.Timeout("slow")
        return real_post(url, **kw)

    monkeypatch.setattr(requests, "post", post)
    assert run(load_brander()) == 24


# --- the edit form is all or nothing ---------------------------------------------------


def test_a_bad_setting_does_not_leave_a_refreshed_script(tmp_path):
    from tests.test_brander_settings import SOURCE, deployed
    from views._type_handlers.tap_handler import _apply_brander_settings
    from views._type_handlers.base import AutomationError

    path = deployed(tmp_path)
    text = open(path).read().replace("def preflight", "def _old_preflight")
    open(path, "w").write(text)
    form = {
        "brander_refresh": "on",
        "brander_template_path": "legacy",
        "brander_max_kb": "5",
        "brander_wallpaper_setting": "3",
        "brander_allow_person_fields": "no",
    }
    with pytest.raises(AutomationError):
        _apply_brander_settings(path, form)
    assert open(path).read() == text
    assert SOURCE


# --- cooldowns are written atomically ----------------------------------------------------


def test_json_writes_are_atomic(tmp_path, monkeypatch):
    target = tmp_path / "cool.json"
    target.write_text(json.dumps({"keep": 1}))

    def explode(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", explode)
    with pytest.raises(OSError):
        data_store._write_json(str(target), {"new": 2})
    assert json.loads(target.read_text()) == {"keep": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["cool.json"]


# --- the unauthenticated confirm POST is rate-limited ---------------------------------


def test_confirm_posts_are_rate_limited_per_address(
    client, jawa_env, monkeypatch
):
    from tests.test_tap_receiver import (
        GOOD_QUERY,
        RecordingPopen,
        _make_service,
    )
    from webhook import tap_receiver
    import subprocess

    RecordingPopen.calls = []
    RecordingPopen.return_code = 0
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    monkeypatch.setattr(tap_receiver, "_now", lambda: 1000.0)
    tap_receiver.reset_rate_limits()
    _make_service(jawa_env)
    statuses = [
        client.post(
            "/tap/reset-ipad", data=dict(GOOD_QUERY, id=str(100 + i))
        ).status_code
        for i in range(12)
    ]
    assert statuses[:10] == [200] * 10
    assert statuses[10:] == [429, 429]
    assert len(RecordingPopen.calls) == 10
    # Another address is unaffected, and the window moves on.
    other = client.post(
        "/tap/reset-ipad",
        data=GOOD_QUERY,
        environ_base={"REMOTE_ADDR": "10.9.9.9"},
    )
    assert other.status_code == 200
    monkeypatch.setattr(tap_receiver, "_now", lambda: 1061.0)
    assert (
        client.post(
            "/tap/reset-ipad", data=dict(GOOD_QUERY, id="200")
        ).status_code
        == 200
    )
