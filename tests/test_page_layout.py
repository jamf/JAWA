"""J41 page layout: one compact hero band everywhere, the log page fills
the window, and the log toolbar has a phone level menu."""

import pytest
from flask import render_template_string


def test_the_hero_macro_renders_the_band():
    from app import app

    with app.test_request_context():
        html = render_template_string(
            '{% from "shared/_macros.html" import hero_section %}'
            '{{ hero_section(title="T", subtitle="S", create_url="/x", create_label="Go") }}'
        )
    assert '<div class="hero-section">' in html and 'class="hero-cta"' in html


@pytest.mark.parametrize(
    "path", ["/dashboard", "/log/home.html", "/setup", "/resources/files"]
)
def test_pages_use_the_single_hero_style(logged_in_client, jawa_env, path):
    body = logged_in_client.get(path).get_data(as_text=True)
    assert 'class="hero-section"' in body
    assert "hero-section--" not in body


def test_the_log_page_fills_the_window(logged_in_client, jawa_env):
    body = logged_in_client.get("/log/home.html").get_data(as_text=True)
    assert 'class="jawa-bg d-flex flex-column page-fill"' in body
    assert 'id="levelSelect"' in body


def test_other_pages_scroll_normally(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").get_data(as_text=True)
    assert "page-fill" not in body


def test_the_sign_in_icon_scales(client, jawa_env):
    body = client.get("/home.html").get_data(as_text=True)
    assert 'class="img-fluid login-icon"' in body
