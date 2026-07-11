"""Upload size cap (J10). Flask MAX_CONTENT_LENGTH rejects oversized bodies.

Also covers shebang validation on automation script uploads (J10): a script
without a ``#!`` first line must be rejected AT UPLOAD, not cryptically at
trigger time when the receiver ``Popen``-execs it directly.
"""

import io
import os

import pytest

import app as jawa_app


def test_max_content_length_is_set_to_16mb():
    assert jawa_app.app.config.get("MAX_CONTENT_LENGTH") == 16 * 1024 * 1024


def test_oversized_upload_is_rejected(logged_in_client, jawa_env):
    # A body over 16 MB must be rejected (413), not silently accepted.
    big = b"x" * (16 * 1024 * 1024 + 1024)
    resp = logged_in_client.post(
        "/resources/files",
        data={"upload": (io.BytesIO(big), "big.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413


class _FakeFile:
    """Minimal werkzeug FileStorage stand-in backed by bytes."""

    def __init__(self, filename, content):
        self.filename = filename
        self._stream = io.BytesIO(content)

    def read(self, n=-1):
        return self._stream.read(n)

    def seek(self, pos, whence=0):
        return self._stream.seek(pos, whence)

    def save(self, path):
        self._stream.seek(0)
        with open(path, "wb") as f:
            f.write(self._stream.read())


def test_save_script_rejects_missing_shebang(jawa_env):
    from bin import data_store

    bad = _FakeFile("noshebang.sh", b"echo hello\n")
    with pytest.raises(ValueError):
        data_store.save_script(bad, "test")
    # Nothing should have been written for a rejected upload.
    assert os.listdir(data_store.SCRIPTS_DIR) == []


def test_save_script_accepts_shebang(jawa_env):
    from bin import data_store

    good = _FakeFile("good.sh", b"#!/bin/bash\necho hi\n")
    path = data_store.save_script(good, "test")
    assert os.path.exists(path)
    # The rewind must let save() write the FULL file, not just the tail.
    with open(path, "rb") as f:
        assert f.read() == b"#!/bin/bash\necho hi\n"
