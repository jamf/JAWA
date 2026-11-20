"""Every named form field has a visible <label for> that matches its id."""

from html.parser import HTMLParser

import pytest
from flask import render_template

import app as jawa_app

CONTROLS = ("input", "textarea", "select")


class _Fields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.label_for = set()
        self.controls = []  # (name, id)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "label" and attrs.get("for"):
            self.label_for.add(attrs["for"])
        elif tag in CONTROLS and attrs.get("name"):
            if attrs.get("type") not in ("hidden", "submit"):
                self.controls.append((attrs["name"], attrs.get("id")))


def unlabelled(html):
    parser = _Fields()
    parser.feed(html)
    assert parser.controls, "no form fields rendered"
    return [
        name
        for name, ident in parser.controls
        if not ident or ident not in parser.label_for
    ]


TAP_INFO = {
    "name": "reset-ipad",
    "description": "",
    "device_family": "mobile",
    "cooldown_minutes": 0,
    "page_title": "{DEVICENAME}",
    "page_description": "Reset this device.",
    "confirm_label": "Reset",
    "success_message": "Done.",
    "failure_message": "Failed.",
    "webclip_label": "",
    "jamf_id": None,
}

BRANDER_SETTINGS = {
    "template_path": "legacy",
    "wallpaper_setting": 1,
    "max_kb": 500,
    "allow_person_fields": "no",
}


@pytest.mark.parametrize(
    "context",
    [
        pytest.param({"edit_mode": False, "webhook_info": []}, id="create"),
        pytest.param(
            {
                "edit_mode": True,
                "webhook_info": [TAP_INFO],
                "brander_settings": BRANDER_SETTINGS,
                "brander_template_options": ["legacy"],
            },
            id="edit",
        ),
    ],
)
def test_tap_fields_are_labelled(jawa_env, context):
    with jawa_app.app.test_request_context("/"):
        html = render_template(
            "automations/_partials/_tap_fields.html",
            device_families=["mobile", "computer"],
            **context,
        )
    assert unlabelled(html) == []


def test_login_form_is_labelled(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="password"' in body
    assert unlabelled(body) == []
