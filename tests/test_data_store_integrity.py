"""JSON stores are written atomically and a corrupt file is never emptied."""

import json
import os

import pytest

from bin import data_store


def test_truncated_webhooks_file_is_not_read_as_empty(jawa_env):
    jawa_env.add_webhook({"name": "keepme", "tag": "custom"})
    good = jawa_env.webhooks_file.read_text()
    truncated = good[: len(good) // 2]
    jawa_env.webhooks_file.write_text(truncated)

    with pytest.raises(data_store.StoreCorruptError):
        data_store.get_all_webhooks()
    with pytest.raises(data_store.StoreCorruptError):
        data_store.add_webhook({"name": "other", "tag": "custom"})

    # Nothing overwrote the damaged file, so the automations can be recovered.
    assert jawa_env.webhooks_file.read_text() == truncated


def test_corrupt_credentials_file_is_not_overwritten(
    logged_in_client, jawa_env
):
    jawa_env.credentials_file.write_text('[{"name": "a", "usern')
    with pytest.raises(data_store.StoreCorruptError):
        logged_in_client.get("/setup/credentials")
    assert jawa_env.credentials_file.read_text() == '[{"name": "a", "usern'


def test_write_replaces_atomically_and_leaves_no_temp_files(
    jawa_env, monkeypatch
):
    jawa_env.add_webhook({"name": "first", "tag": "custom"})
    before = jawa_env.webhooks_file.read_text()

    def boom(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        data_store.add_webhook({"name": "second", "tag": "custom"})
    monkeypatch.undo()

    assert jawa_env.webhooks_file.read_text() == before
    assert [p.name for p in jawa_env.data_dir.iterdir() if p.name.startswith(".tmp-")] == []


def test_write_fsyncs_before_replace(jawa_env, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    data_store.atomic_write_json(str(jawa_env.data_dir / "x.json"), {"a": 1})
    assert order == ["fsync", "replace"]
    assert json.loads((jawa_env.data_dir / "x.json").read_text()) == {"a": 1}


def _mode(path):
    import os
    import stat
    return stat.S_IMODE(os.stat(path).st_mode)


def test_saving_a_credential_set_leaves_the_file_owner_only(
    logged_in_client, jawa_env
):
    import os
    os.chmod(jawa_env.credentials_file, 0o644)
    resp = logged_in_client.post(
        "/setup/credentials/add",
        data={"name": "prod", "server_url": "https://jamf.example.test",
              "client_id": "id", "client_secret": "s3cret"},
    )
    assert resp.status_code == 302
    assert "s3cret" in jawa_env.credentials_file.read_text()
    assert _mode(jawa_env.credentials_file) == 0o600


def test_saving_a_webhook_leaves_the_file_owner_only(jawa_env):
    import os
    os.chmod(jawa_env.webhooks_file, 0o644)
    data_store.add_webhook({"name": "w", "tag": "custom", "api_key": "k"})
    assert _mode(jawa_env.webhooks_file) == 0o600


def test_start_up_tightens_existing_secret_files(jawa_env):
    import os
    for path in (jawa_env.webhooks_file, jawa_env.credentials_file):
        os.chmod(path, 0o644)
    data_store.secure_private_files(
        [str(jawa_env.webhooks_file), str(jawa_env.credentials_file),
         str(jawa_env.data_dir / "missing.json")]
    )
    assert _mode(jawa_env.webhooks_file) == 0o600
    assert _mode(jawa_env.credentials_file) == 0o600
