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
