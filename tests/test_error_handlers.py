"""Branded 500/405 error handlers (J7/B5)."""

import app as jawa_app


def test_500_renders_branded_page_no_traceback(jawa_env):
    # The app is a long-lived singleton that has already served requests,
    # so a fresh route cannot be registered mid-suite. Invoke the handler
    # directly inside a request context instead: the assertions that matter
    # are the 500 status and that the internal detail is never leaked.
    exc = RuntimeError("kaboom-secret-detail")
    with jawa_app.app.test_request_context("/_boom_test"):
        from flask import session

        session["username"] = "pytest-admin"
        session["url"] = "https://jamf.example.test"
        body, status = jawa_app.internal_error(exc)

    assert status == 500
    # Branded page rendered; internal exception detail not leaked.
    assert "error-card" in body
    assert "kaboom-secret-detail" not in body


def test_405_renders_branded_page(logged_in_client):
    # /dashboard is GET-only; POST should 405 via the branded handler.
    resp = logged_in_client.post("/dashboard")
    assert resp.status_code == 405
    body = resp.data.decode()
    assert "error-card" in body
    assert "Method not allowed" in body


def test_error_route_does_not_swap_title_and_message(logged_in_client):
    # /error reads ?error=<title>&error_message=<body>. error.html renders
    # `error` as the h1 title and `error_message` as the body. Assert each
    # lands in the correct element so a future arg-swap regresses the test.
    import re

    resp = logged_in_client.get(
        "/error?error=SwapTitleXYZ&error_message=SwapBodyXYZ"
    )
    body = resp.data.decode()
    # Title belongs in the error-title heading, not the body.
    title_match = re.search(
        r'class="error-title"[^>]*>(.*?)</h1>', body, re.DOTALL
    )
    assert title_match and "SwapTitleXYZ" in title_match.group(1)
    # Message belongs in the error-message block.
    msg_match = re.search(
        r'class="error-message"[^>]*>(.*?)</div>', body, re.DOTALL
    )
    assert msg_match and "SwapBodyXYZ" in msg_match.group(1)
