"""Brander (Asset Tag Watch): the timed template that re-brands a device
when its asset tag or Brander extension attribute changes.

The script is loaded with its tokens filled, Jamf Pro is faked at the
``requests`` layer and the Brander subprocess at ``subprocess.run``. No
network and no real Brander run.
"""

import json
import os
import sqlite3
import subprocess
import sys
import types

import pytest
import requests
from crontab import CronTab

from bin import data_store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "data", "workflows", "scripts")
SCRIPT = os.path.join(SCRIPTS, "asset_tag_brander.py")
SERVER = "https://jamf.example.test"
SECRET = "pytest-client-secret-value"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class FakeJamf:
    """Mobile devices keyed by id; each is (general, extension_attributes)."""

    def __init__(self):
        self.devices = {}
        self.list_fails = False

    def device(self, jps_id, asset_tag="", brander="On", udid=None, **general):
        general.setdefault("barcode_1", "")
        general.setdefault("barcode_2", "")
        self.devices[jps_id] = (
            {
                "asset_tag": asset_tag,
                "serial_number": f"SER{jps_id}",
                "device_name": f"iPad {jps_id}",
                "udid": udid or f"udid-{jps_id}",
                **general,
            },
            [{"id": 7, "name": "Brander", "value": brander}],
        )

    def post(self, url, **kwargs):
        return FakeResponse({"access_token": "tok", "expires_in": 600})

    def request(self, method, url, **kwargs):
        path = url.split("/JSSResource/", 1)[1]
        if path == "mobiledevices":
            if self.list_fails:
                return FakeResponse({}, status_code=500)
            return FakeResponse(
                {"mobile_devices": [{"id": i} for i in sorted(self.devices)]}
            )
        jps_id = int(path.rsplit("/", 1)[1])
        general, eas = self.devices[jps_id]
        return FakeResponse(
            {
                "mobile_device": {
                    "general": dict(general),
                    "extension_attributes": list(eas),
                }
            }
        )


class FakeRun:
    """subprocess.run stand-in: exit code per device id (default 0)."""

    def __init__(self):
        self.calls = []
        self.codes = {}
        self.timeout_ids = set()

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        jps_id = json.loads(argv[2])["event"]["jssID"]
        if jps_id in self.timeout_ids:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return subprocess.CompletedProcess(
            argv,
            self.codes.get(jps_id, 0),
            stdout="Brander said ok\n",
            stderr="",
        )


@pytest.fixture()
def watch(tmp_path, monkeypatch):
    jamf = FakeJamf()
    run = FakeRun()
    monkeypatch.setattr(requests, "post", jamf.post)
    monkeypatch.setattr(requests, "request", jamf.request)
    monkeypatch.setattr(subprocess, "run", run)
    brander = tmp_path / "brand-device.py"
    brander.write_text("#!/usr/bin/env python3\n")
    db = tmp_path / "watch.sqlite"
    values = {
        '"__JAWA_SERVER_URL__"': repr(SERVER),
        '"__JAWA_CLIENT_ID__"': repr("pytest-client"),
        '"__JAWA_CLIENT_SECRET__"': repr(SECRET),
        '"__JAWA_DB_PATH__"': repr(str(db)),
        '"__JAWA_BRANDER_SCRIPT__"': repr(str(brander)),
    }

    def load(dry_run="no"):
        source = open(SCRIPT, encoding="utf-8").read()
        filled = dict(values, **{'"__JAWA_DRY_RUN__"': repr(dry_run)})
        for token, value in filled.items():
            source = source.replace(token, value)
        assert "__JAWA_" not in source
        module = types.ModuleType("asset_tag_brander")
        exec(compile(source, SCRIPT, "exec"), module.__dict__)
        return module

    def main(capsys, dry_run="no"):
        module = load(dry_run)
        try:
            module.main()
            code = 0
        except SystemExit as stop:
            code = stop.code
        return code, capsys.readouterr().out

    def row(jps_id):
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        found = conn.execute(
            "SELECT * FROM asset_and_ea_tracking WHERE jps_id = ?", (jps_id,)
        ).fetchone()
        conn.close()
        return dict(found) if found else None

    return types.SimpleNamespace(
        jamf=jamf,
        run=run,
        db=db,
        brander=brander,
        load=load,
        main=main,
        row=row,
    )


def test_first_run_seeds_without_branding(watch, capsys):
    watch.jamf.device(1, asset_tag="A1")
    watch.jamf.device(2, asset_tag="B1")
    code, out = watch.main(capsys)
    assert code == 0
    assert watch.run.calls == []
    assert watch.row(1)["current_asset_tag"] == "A1"
    assert watch.row(2)["current_brander_ea"] == "On"
    assert "2 devices checked, 0 changed, 0 branded, 0 failed" in out


def test_asset_tag_change_brands_with_id_and_udid(watch, capsys):
    watch.jamf.device(42, asset_tag="A1", udid="ABC-UDID-42")
    watch.main(capsys)
    watch.jamf.device(42, asset_tag="A2", udid="ABC-UDID-42")
    code, out = watch.main(capsys)

    assert code == 0
    assert len(watch.run.calls) == 1
    argv, kwargs = watch.run.calls[0]
    assert argv[0] == sys.executable
    assert argv[1] == str(watch.brander)
    assert json.loads(argv[2]) == {
        "event": {"jssID": 42, "udid": "ABC-UDID-42"}
    }
    assert kwargs["timeout"] == 300
    stored = watch.row(42)
    assert stored["current_asset_tag"] == "A2"
    assert stored["previous_asset_tag"] == "A1"
    assert stored["asset_tag_change_count"] == 1
    assert stored["total_change_count"] == 1
    assert stored["last_change_timestamp"]
    assert "device 42: asset tag 'A1' -> 'A2'" in out
    assert "1 devices checked, 1 changed, 1 branded, 0 failed" in out
    # Neither the UDID nor the client secret reaches the log.
    assert "ABC-UDID-42" not in out
    assert SECRET not in out


def test_brander_ea_change_brands(watch, capsys):
    watch.jamf.device(5, asset_tag="T5", brander="Off")
    watch.main(capsys)
    watch.jamf.device(5, asset_tag="T5", brander="On")
    code, out = watch.main(capsys)
    assert code == 0
    assert len(watch.run.calls) == 1
    stored = watch.row(5)
    assert (stored["current_brander_ea"], stored["previous_brander_ea"]) == (
        "On",
        "Off",
    )
    assert stored["brander_ea_change_count"] == 1
    assert stored["asset_tag_change_count"] == 0
    assert "device 5: Brander EA 'Off' -> 'On'" in out


def test_barcode_fallback(watch, capsys):
    watch.jamf.device(3, asset_tag="", barcode_1="", barcode_2="BC2")
    watch.main(capsys)
    assert watch.row(3)["current_asset_tag"] == "BC2"
    watch.jamf.device(3, asset_tag="n/a", barcode_1="BC1", barcode_2="BC2")
    watch.main(capsys)
    assert len(watch.run.calls) == 1
    assert watch.row(3)["current_asset_tag"] == "BC1"


@pytest.mark.parametrize(
    "empty", ["", "  ", "null", "NULL", "None", "N/A", "n/a"]
)
def test_empty_spellings_are_all_empty(watch, capsys, empty):
    watch.jamf.device(9, asset_tag="", brander="")
    watch.main(capsys)
    assert watch.row(9)["current_asset_tag"] is None
    assert watch.row(9)["current_brander_ea"] is None
    watch.jamf.device(9, asset_tag=empty, brander=empty)
    code, out = watch.main(capsys)
    assert code == 0
    assert watch.run.calls == []
    assert "0 changed" in out


def test_unhandled_exit_keeps_old_values_and_retries(watch, capsys):
    watch.jamf.device(7, asset_tag="OLD")
    watch.main(capsys)
    before = watch.row(7)

    watch.jamf.device(7, asset_tag="NEW")
    watch.run.codes[7] = 24
    code, out = watch.main(capsys)
    assert code == 2
    assert watch.row(7) == before, "a failed brand must not store the new tag"
    assert "1 failed" in out

    # Next run sees the same change and tries again; this time it lands.
    watch.run.codes[7] = 0
    code, out = watch.main(capsys)
    assert code == 0
    assert len(watch.run.calls) == 2
    assert watch.row(7)["current_asset_tag"] == "NEW"
    assert watch.row(7)["previous_asset_tag"] == "OLD"


def test_timeout_is_not_handled(watch, capsys):
    watch.jamf.device(8, asset_tag="OLD")
    watch.main(capsys)
    watch.jamf.device(8, asset_tag="NEW")
    watch.run.timeout_ids.add(8)
    code, _ = watch.main(capsys)
    assert code == 2
    assert watch.row(8)["current_asset_tag"] == "OLD"


@pytest.mark.parametrize("exit_code", [0, 42, 25, 26])
def test_settled_brander_exits_count_as_handled(watch, capsys, exit_code):
    watch.jamf.device(4, asset_tag="OLD")
    watch.main(capsys)
    watch.jamf.device(4, asset_tag="NEW")
    watch.run.codes[4] = exit_code
    code, out = watch.main(capsys)
    assert code == 0
    assert watch.row(4)["current_asset_tag"] == "NEW"
    assert "0 failed" in out


def test_one_failure_does_not_stop_the_next_device(watch, capsys):
    watch.jamf.device(1, asset_tag="A")
    watch.jamf.device(2, asset_tag="B")
    watch.main(capsys)
    watch.jamf.device(1, asset_tag="A2")
    watch.jamf.device(2, asset_tag="B2")
    watch.run.codes[1] = 24
    code, out = watch.main(capsys)
    assert code == 2
    assert len(watch.run.calls) == 2
    assert watch.row(1)["current_asset_tag"] == "A"
    assert watch.row(2)["current_asset_tag"] == "B2"
    assert "2 devices checked, 2 changed, 1 branded, 1 failed" in out


def test_dry_run_calls_nothing_and_stores_nothing(watch, capsys):
    watch.jamf.device(6, asset_tag="OLD")
    watch.main(capsys)
    before = watch.row(6)
    watch.jamf.device(6, asset_tag="NEW")
    code, out = watch.main(capsys, dry_run="yes")
    assert code == 0
    assert watch.run.calls == []
    assert watch.row(6) == before
    assert "device 6: asset tag 'OLD' -> 'NEW'" in out
    assert "would run Brander" in out


def test_device_list_failure_exits_and_leaves_the_db_alone(watch, capsys):
    watch.jamf.device(1, asset_tag="A")
    watch.main(capsys)
    before = watch.db.read_bytes()
    watch.jamf.device(1, asset_tag="B")
    watch.jamf.list_fails = True
    code, out = watch.main(capsys)
    assert code == 1
    assert watch.db.read_bytes() == before
    assert watch.run.calls == []


def test_device_list_failure_on_a_fresh_host_creates_no_db(watch, capsys):
    watch.jamf.list_fails = True
    code, _ = watch.main(capsys)
    assert code == 1
    assert not watch.db.exists()


def test_a_run_still_going_makes_the_next_one_skip(watch, capsys):
    import fcntl

    watch.jamf.device(1, asset_tag="A")
    watch.main(capsys)
    watch.jamf.device(1, asset_tag="B")
    held = open(str(watch.db) + ".lock", "w")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        code, out = watch.main(capsys)
    finally:
        held.close()
    assert code == 0
    assert "previous run is still going" in out
    assert watch.run.calls == []
    assert watch.row(1)["current_asset_tag"] == "A"
    code, _ = watch.main(capsys)
    assert code == 0
    assert len(watch.run.calls) == 1


def _canonical(path):
    source = open(path, encoding="utf-8").read()
    start = source.index("# --- JAWA canonical Jamf API block")
    end = source.index("# --- end canonical block ---")
    return source[start : end + len("# --- end canonical block ---")]


def test_canonical_block_is_byte_identical_to_tap_brander():
    assert _canonical(SCRIPT) == _canonical(
        os.path.join(SCRIPTS, "tap_brander.py")
    )


# ---- enabling it from the catalog ----


class _RecordingTab:
    def __init__(self):
        self.written = None

    def __call__(self, user=None):
        factory = self

        class Memory(CronTab):
            def write(self, *args, **kwargs):
                factory.written = self.render()

        return Memory(tab="")


@pytest.fixture()
def tab(monkeypatch):
    from views._type_handlers import cron_handler

    recording = _RecordingTab()
    monkeypatch.setattr(cron_handler, "CronTab", recording)
    return recording


def test_enabling_creates_a_timed_automation(
    logged_in_client, jawa_env, enable_form, tab
):
    form = enable_form("asset-tag-brander", webhook_name="asset-tag-brander")
    # The optional settings left blank take their catalog defaults.
    for key in ("brander_script", "db_path", "dry_run"):
        form[key] = ""
    resp = logged_in_client.post(
        "/templates/asset-tag-brander/enable", data=form
    )

    assert resp.status_code == 302
    assert "/error" not in resp.headers["Location"]
    entry = data_store.get_cron_by_name("asset-tag-brander")
    assert entry is not None
    assert data_store.get_webhook_by_name("asset-tag-brander") is None
    line = next(
        row
        for row in tab.written.splitlines()
        if row.endswith("# asset-tag-brander")
    )
    assert line.startswith("*/15 * * * * ")
    assert "bin/run_cron.py asset-tag-brander" in line

    deployed = open(entry["script"], encoding="utf-8").read()
    assert "__JAWA_" not in deployed
    namespace = {}
    exec(compile(deployed, entry["script"], "exec"), namespace)
    assert (
        namespace["BRANDER_SCRIPT"]
        == "/usr/local/jawa/scripts/brand-device.py"
    )
    assert (
        namespace["DB_PATH"] == "/usr/local/jawa/data/asset_tag_watch.sqlite"
    )
    assert namespace["DRY_RUN"] == "no"
    assert namespace["Config"]().server_url == form["server_url"]


def test_enabling_honours_a_chosen_schedule(
    logged_in_client, jawa_env, enable_form, tab
):
    form = enable_form(
        "asset-tag-brander", webhook_name="watch-5", schedule="*/5 * * * *"
    )
    logged_in_client.post("/templates/asset-tag-brander/enable", data=form)
    line = next(r for r in tab.written.splitlines() if r.endswith("# watch-5"))
    assert line.startswith("*/5 * * * * ")


def test_a_bad_schedule_writes_nothing(
    logged_in_client, jawa_env, enable_form, tab
):
    form = enable_form(
        "asset-tag-brander",
        webhook_name="bad-watch",
        schedule="every so often",
    )
    resp = logged_in_client.post(
        "/templates/asset-tag-brander/enable", data=form
    )
    assert "/error" in resp.headers["Location"]
    assert tab.written is None
    assert data_store.get_cron_by_name("bad-watch") is None
    assert not os.listdir(str(jawa_env.scripts_dir))


def test_enable_form_offers_a_schedule_and_no_webhook_auth(
    logged_in_client, jawa_env
):
    body = logged_in_client.get(
        "/templates/asset-tag-brander/enable"
    ).get_data(as_text=True)
    assert 'name="schedule"' in body
    assert 'value="*/15 * * * *"' in body
    assert 'name="event"' not in body
    assert "Webhook Authentication" not in body
