"""The fork's own pages (Tap Action and Brander) use the vendored roster
CSS; the Jamf console pages do not load it."""

import os
import re

import pytest

from tests.test_tap_templates import _SERVICE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(REPO_ROOT, "static", "css", "vendor")
ROSTER_CSS = (
    "/static/css/vendor/roster-web.css",
    "/static/css/vendor/roster-html.css",
)


@pytest.mark.parametrize(
    "name", ["roster-web.css", "roster-html.css", "icons.svg"]
)
def test_vendored_files_carry_their_version_stamp(name):
    with open(os.path.join(VENDOR, name), encoding="utf-8") as handle:
        first = handle.readline()
    assert re.search(
        r"roster-bridge \S+ from @blakesteve/roster \S+ "
        + re.escape(name)
        + " sha256:",
        first,
    )


def test_vendored_files_keep_the_licence_notice():
    with open(os.path.join(VENDOR, "README.md"), encoding="utf-8") as handle:
        text = handle.read()
    assert (
        "MIT" in text and "@blakesteve/roster" in text and "CC BY 4.0" in text
    )


@pytest.mark.parametrize("path", ["/brander/templates", "/brander/preview"])
def test_brander_pages_load_roster_and_have_no_inline_style(
    logged_in_client, jawa_env, path
):
    body = logged_in_client.get(path).get_data(as_text=True)
    for href in ROSTER_CSS:
        assert href in body
    assert "<style" not in body
    assert "rb-btn" in body


def test_tap_pages_load_roster(client, jawa_env):
    jawa_env.add_webhook(dict(_SERVICE))
    body = client.get(
        "/tap/reset-ipad",
        query_string={"token": _SERVICE["token"], "id": "7", "udid": "UDID-1"},
    ).get_data(as_text=True)
    for href in ROSTER_CSS:
        assert href in body
    assert "<style" not in body
    assert 'class="rb-btn rb-btn--lg"' in body


@pytest.mark.parametrize(
    "state, kind",
    [
        ("success", "rb-alert--ok"),
        ("failure", "#circle-exclamation"),
        ("cooldown", "rb-alert--warn"),
    ],
)
def test_tap_results_are_alerts_with_an_icon(
    logged_in_client, jawa_env, state, kind
):
    jawa_env.add_webhook(dict(_SERVICE))
    body = logged_in_client.get(
        f"/automations/tap/reset-ipad/preview?state={state}"
    ).get_data(as_text=True)
    assert kind in body
    # The icon symbols are inline: the sandboxed preview frame cannot load
    # the sprite file, and a device page then needs no second request.
    use = re.search(r'use href=(?:"|&#34;|&quot;)#([a-z-]+)', body)
    assert use, "the alert has no inline icon"
    assert (
        f"symbol id=&#34;{use.group(1)}&#34;" in body
        or f"symbol id=&quot;{use.group(1)}&quot;" in body
    )


@pytest.mark.parametrize("path", ["/dashboard", "/automations", "/templates"])
def test_console_pages_do_not_load_roster(logged_in_client, jawa_env, path):
    body = logged_in_client.get(path).get_data(as_text=True)
    assert "css/vendor/" not in body


def _css(name):
    with open(
        os.path.join(REPO_ROOT, "static", "css", name), encoding="utf-8"
    ) as handle:
        return handle.read()


def test_tap_pages_keep_jawas_own_palette():
    # Roster supplies the parts; the colours stay JAWA's Tap Action palette.
    css = _css("tap.css")
    assert "--ss-accent: #1d4ed8;" in css
    assert "--roster-primary-600: var(--ss-accent);" in css
    assert "--rb-surface: var(--ss-bg);" in css


def test_brander_pages_use_the_console_palette():
    # The Brander pages sit inside the console, so roster's tokens point at
    # main.css's variables and follow its dark mode.
    css = _css("brander.css")
    assert "--roster-primary-600: var(--color-primary);" in css
    assert "--roster-card-bg: var(--color-surface);" in css
    assert "@media (prefers-color-scheme: dark)" in css
