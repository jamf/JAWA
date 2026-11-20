"""Timed automations run through bin/run_cron.py, so they log like webhooks."""

import io
import json
import logging
import sys

from crontab import CronTab


class _RecordingTab:
    """A CronTab factory over fixed text that keeps what would be written."""

    def __init__(self, text=""):
        self.text = text
        self.written = None

    def __call__(self, user=None):
        factory = self

        class Memory(CronTab):
            def write(self, *args, **kwargs):
                factory.written = self.render()

        return Memory(tab=self.text)


def _add_cron(jawa_env, name, script):
    data = json.loads(jawa_env.cron_file.read_text())
    data.append(
        {
            "name": name,
            "description": "",
            "frequency": "Every day at 2:00 AM",
            "script": script,
        }
    )
    jawa_env.cron_file.write_text(json.dumps(data))


def test_run_cron_logs_output_and_failure(jawa_env, caplog):
    from bin import run_cron

    stub = jawa_env.scripts_dir / "cron_NightlyExport.sh"
    stub.write_text("#!/bin/sh\necho first line\necho second line\nexit 3\n")
    stub.chmod(0o700)
    _add_cron(jawa_env, "NightlyExport", str(stub))

    with caplog.at_level(logging.INFO, logger="jawa"):
        code = run_cron.main(["NightlyExport"])

    assert code == 3
    messages = [r.getMessage() for r in caplog.records]
    assert "NightlyExport - first line" in messages
    assert "NightlyExport - second line" in messages
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "NightlyExport" in errors[0].getMessage()
    assert "exit code 3" in errors[0].getMessage()


def test_run_cron_unknown_name_is_an_error(jawa_env, caplog):
    from bin import run_cron

    with caplog.at_level(logging.INFO, logger="jawa"):
        code = run_cron.main(["Missing"])

    assert code == 1
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_creating_timed_automation_writes_run_cron_line(
    logged_in_client, jawa_env, monkeypatch
):
    from views._type_handlers import cron_handler

    tab = _RecordingTab("")
    monkeypatch.setattr(cron_handler, "CronTab", tab)
    resp = logged_in_client.post(
        "/automations/cron/new",
        data={
            "cron_name": "Created",
            "frequency": "everyday",
            "daytime": "2",
            "script": (io.BytesIO(b"#!/bin/sh\ntrue\n"), "job.sh"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert tab.written is not None
    line = next(
        row for row in tab.written.splitlines() if row.endswith("# Created")
    )
    assert sys.executable in line
    assert "bin/run_cron.py Created" in line


def test_startup_migration_rewrites_only_jawa_lines(jawa_env, monkeypatch):
    from views._type_handlers import cron_handler

    script = str(jawa_env.scripts_dir / "cron_NightlyExport.sh")
    _add_cron(jawa_env, "NightlyExport", script)
    tab = _RecordingTab(
        f"0 2 * * * {script} # NightlyExport\n"
        "5 4 * * * /usr/local/bin/backup # SomethingElse\n"
    )
    monkeypatch.setattr(cron_handler, "CronTab", tab)

    assert cron_handler.migrate_cron_commands() == 1
    rows = tab.written.splitlines()
    ours = next(row for row in rows if row.endswith("# NightlyExport"))
    assert ours.startswith("0 2 * * * ")
    assert "bin/run_cron.py NightlyExport" in ours
    assert "5 4 * * * /usr/local/bin/backup # SomethingElse" in rows

    # Already migrated: nothing to change, nothing written.
    tab.text = tab.written
    tab.written = None
    assert cron_handler.migrate_cron_commands() == 0
    assert tab.written is None
