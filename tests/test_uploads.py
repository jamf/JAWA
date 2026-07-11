"""Upload size cap (J10). Flask MAX_CONTENT_LENGTH rejects oversized bodies."""

import app as jawa_app


def test_max_content_length_is_set_to_16mb():
    assert jawa_app.app.config.get("MAX_CONTENT_LENGTH") == 16 * 1024 * 1024


def test_oversized_upload_is_rejected(logged_in_client, jawa_env):
    # A body over 16 MB must be rejected (413), not silently accepted.
    big = b"x" * (16 * 1024 * 1024 + 1024)
    resp = logged_in_client.post(
        "/resources/files",
        data={"upload": (__import__("io").BytesIO(big), "big.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
