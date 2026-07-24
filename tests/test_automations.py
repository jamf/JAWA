"""Automation create/edit/delete success flow: PRG + one-shot flash."""

import io


def _custom_create_data():
    # custom_handler.process_create requires a name + an uploaded script.
    return {
        "custom_name": "prg-test-hook",
        "description": "prg test",
        "new_file": (io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
                     "hook.py"),
    }


def test_create_redirects_to_success(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    # PRG: the POST must 302 to /success, not render 200 inline.
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_success_flash_is_one_shot(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    # First GET renders the flashed context; second GET has no flash left.
    first = logged_in_client.get("/success")
    assert first.status_code == 200
    assert b"New webhook created" in first.data
    second = logged_in_client.get("/success")
    # Flash popped: the create message must not persist on a re-load.
    assert b"New webhook created" not in second.data


def test_edit_redirects_to_success(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    logged_in_client.get("/success")  # drain the create flash
    resp = logged_in_client.post(
        "/automations/custom/prg-test-hook/edit",
        data={
            "custom_name": "prg-test-hook",
            "description": "edited",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_delete_redirects_to_success(logged_in_client, jawa_env):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    logged_in_client.get("/success")
    resp = logged_in_client.post(
        "/automations/custom/prg-test-hook/delete",
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]
