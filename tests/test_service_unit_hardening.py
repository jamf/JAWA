"""The jawa.service unit must ship the sandboxing directives from the
2026-11 security audit.

The audit's plaintext-secrets-data-dir finding drove 0600 credential files
(data_store.atomic_write_json(private=True)) and startup tightening
(secure_private_files). Both only protect files the app already knows about;
the unit-level umask and sandbox are the outer layer that keeps anything the
app creates from being group/world-readable in the first place, and bounds
what a compromised process (the receiver runs operator-supplied scripts via
subprocess) can touch.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_DIRECTIVES = (
    # Credential hygiene: every file the service creates lands 0600.
    "UMask=0077",
    # Filesystem fence: the whole tree read-only except the install dir.
    "ProtectSystem=strict",
    "ProtectHome=true",
    "PrivateTmp=true",
    # Process fence: operator-supplied scripts must not poke raw devices.
    "PrivateDevices=true",
)


def _unit_source():
    with open(
        os.path.join(REPO_ROOT, "bin", "installer.sh"), encoding="utf-8"
    ) as handle:
        return handle.read()


def test_service_unit_ships_audit_hardening():
    source = _unit_source()
    start = source.find("[Service]")
    end = source.find("[Install]", start)
    unit = source[start:end]
    for directive in REQUIRED_DIRECTIVES:
        assert directive in unit, (
            f"jawa.service lost its {directive} hardening directive"
        )


def test_install_tree_is_writable_under_protect_system():
    # ProtectSystem=strict makes every path read-only; without the install
    # directory in ReadWritePaths the app could not write data/ at all.
    source = _unit_source()
    start = source.find("[Service]")
    unit = source[start : source.find("[Install]", start)]
    read_write = [
        line.split("=", 1)[1].strip()
        for line in unit.splitlines()
        if line.startswith("ReadWritePaths=")
    ]
    assert read_write, "unit pins no ReadWritePaths"
    entries = " ".join(read_write).split()
    # The install tree plus the cron spool, never a broad path like / or /usr.
    assert entries == ["$installDir", "-/var/spool/cron"], entries


def test_crontab_is_not_blocked_by_the_sandbox():
    # crontab is setgid/setuid; NoNewPrivileges stops it opening the spool,
    # and timed automations are scheduled through it.
    source = _unit_source()
    start = source.find("[Service]")
    unit = source[start : source.find("[Install]", start)]
    assert "NoNewPrivileges=true" not in unit
