"""The log page: filters in the URL, follow mode, and the level buttons."""

import pytest


def test_level_buttons_state_is_not_colour_only(logged_in_client, jawa_env):
    body = logged_in_client.get("/log/home.html").data.decode()
    assert 'data-level="all" aria-pressed="true"' in body
    assert 'data-level="error" aria-pressed="false"' in body
    # The active button also shows a check mark glyph.
    assert 'class="level-check"' in body
    assert "✓" in body


def test_log_page_reads_filters_from_the_url(logged_in_client, jawa_env):
    body = logged_in_client.get("/log/home.html?q=x&level=info").data.decode()
    for needle in (
        "URLSearchParams(location.search)",
        "history.replaceState",
        "scrollToEnd()",
        "Following: updates every 10 s",
        'id="followToggle"',
    ):
        assert needle in body


def test_an_empty_log_says_so(logged_in_client, jawa_env):
    jawa_env.log_file.write_text("")
    body = logged_in_client.get("/log/home.html").data.decode()
    assert "No log entries yet" in body
    assert '<div id="logEmpty">' in body
    assert 'class="empty-state-icon"' in body


def test_a_log_with_lines_has_no_empty_state(logged_in_client, jawa_env):
    jawa_env.log_file.write_text(
        "2026-10-31 09:00:00,000 - jawa - INFO - started\n"
    )
    body = logged_in_client.get("/log/home.html").data.decode()
    # The empty state stays in the page, hidden, so Follow can show it
    # again if the log is rotated away.
    assert '<div id="logEmpty" hidden>' in body
    assert "started" in body


@pytest.mark.parametrize("path", ["/log/live.html", "/log/yield"])
def test_unbounded_live_log_routes_are_gone(logged_in_client, path):
    # Unknown paths fall through to the not-found handler, which sends a
    # signed-in admin to the dashboard.
    resp = logged_in_client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")


def test_follow_updates_in_place_without_reloading(logged_in_client, jawa_env):
    body = logged_in_client.get("/log/home.html?follow=1").data.decode()
    assert "location.reload(); }, FOLLOW_MS" not in body
    assert "fetch('/log/lines'" in body
    assert "replaceChildren" in body


def test_log_lines_returns_the_tail_as_json(logged_in_client, jawa_env):
    jawa_env.log_file.write_text(
        "2026-10-31 09:00:00,000 - jawa - INFO - one\n"
        "2026-10-31 09:00:01,000 - jawa - ERROR - two\n"
    )
    resp = logged_in_client.get("/log/lines")
    assert resp.status_code == 200
    assert resp.get_json()["lines"][-1].endswith("ERROR - two")
    assert len(resp.get_json()["lines"]) == 2


def test_log_lines_needs_a_session(client):
    resp = client.get("/log/lines")
    assert resp.status_code == 401
