"""The session signing key survives restarts."""

import os
import stat

import app as jawa_app


def test_secret_key_is_created_once_and_reused(tmp_path, monkeypatch):
    monkeypatch.delenv("JAWA_SECRET_KEY", raising=False)
    (tmp_path / "data").mkdir()
    first = jawa_app.load_secret_key(str(tmp_path))
    second = jawa_app.load_secret_key(str(tmp_path))
    assert first == second
    assert len(first) == 64
    mode = stat.S_IMODE(os.stat(tmp_path / "data" / ".secret_key").st_mode)
    assert mode == 0o600


def test_secret_key_prefers_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("JAWA_SECRET_KEY", "from-env")
    (tmp_path / "data").mkdir()
    assert jawa_app.load_secret_key(str(tmp_path)) == "from-env"
    assert not (tmp_path / "data" / ".secret_key").exists()
