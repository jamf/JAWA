"""Open-redirect guard tests for legacy redirect routes (bug B8).

The legacy compatibility routes in ``app.py`` and
``views/template_view.py`` interpolate user-controlled values straight
into a redirect path. A value like ``//evil.com`` or ``/\\evil.com``
turns the resulting path into a protocol-relative URL, which the
browser resolves off-site (open redirect / phishing, CodeQL
``py/url-redirection``).

These routes are anonymous-reachable (they are pure 301 shims), so no
authenticated session is required to exercise them.
"""

import pytest

# Payloads that, before the fix, escape the intended local path.
OFF_SITE_PAYLOADS = [
    "//evil.com",
    "/\\evil.com",
    "\\\\evil.com",
    "https://evil.com",
    "//evil.com/edit",
    # All-separator input sanitizes to empty -> must not leave a
    # dangling "//" segment in the local path (defense-in-depth).
    "////",
    "/",
]


def _assert_local_redirect(resp, prefix):
    """A safe redirect stays on this origin under the given prefix."""
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    # Never protocol-relative and never absolute off-site.
    assert not loc.startswith("//"), f"protocol-relative Location: {loc!r}"
    assert not loc.startswith("http"), f"absolute Location: {loc!r}"
    assert "\\" not in loc, f"backslash in Location: {loc!r}"
    # No embedded "//" either: an interpolated separator run can be
    # re-parsed as protocol-relative by intermediaries.
    assert "//" not in loc, f"embedded '//' in Location: {loc!r}"
    assert loc.startswith(prefix), f"Location {loc!r} escaped prefix {prefix!r}"


# ---- app.py single-segment name routes ----

# (path, query-param, resulting prefix)
NAME_ROUTES = [
    ("/webhooks/jamf/edit", "name", "/automations/jamfpro/"),
    ("/webhooks/custom/edit", "name", "/automations/custom/"),
    ("/cron/edit", "name", "/automations/cron/"),
    ("/cron/delete", "target_job", "/automations/cron/"),
]


@pytest.mark.parametrize("path,param,prefix", NAME_ROUTES)
@pytest.mark.parametrize("payload", OFF_SITE_PAYLOADS)
def test_name_route_rejects_off_site(client, path, param, prefix, payload):
    resp = client.get(path, query_string={param: payload})
    _assert_local_redirect(resp, "/automations")


@pytest.mark.parametrize("path,param,prefix", NAME_ROUTES)
def test_name_route_normal_value_redirects(client, path, param, prefix):
    resp = client.get(path, query_string={param: "myhook"})
    _assert_local_redirect(resp, prefix)
    assert resp.headers["Location"].endswith("myhook/edit") or resp.headers[
        "Location"
    ].endswith("myhook/delete")


# ---- app.py webhook delete (target_webhook -> tag lookup) ----


@pytest.mark.parametrize("payload", OFF_SITE_PAYLOADS)
def test_webhook_delete_rejects_off_site(client, jawa_env, payload):
    resp = client.get(
        "/webhooks/delete", query_string={"target_webhook": payload}
    )
    _assert_local_redirect(resp, "/automations")


def test_webhook_delete_normal_value_redirects(client, jawa_env):
    jawa_env.add_webhook({"name": "myhook", "tag": "custom"})
    resp = client.get(
        "/webhooks/delete", query_string={"target_webhook": "myhook"}
    )
    _assert_local_redirect(resp, "/automations/custom/")
    assert resp.headers["Location"].endswith("myhook/delete")


# ---- template_view /workflows/<path:rest> catch-all ----


@pytest.mark.parametrize(
    "path",
    [
        "/workflows///evil.com",
        "/workflows/\\evil.com",
    ],
)
def test_workflows_rest_rejects_off_site(client, path):
    resp = client.get(path)
    # The invariant is simply: this route never emits an OFF-SITE
    # redirect. A 301 must point at a safe local /templates path; any
    # non-redirect response (e.g. Werkzeug merges "///" and the URL map
    # matches a real page -> 200, or a 404) carries no Location and so
    # cannot redirect off-origin.
    loc = resp.headers.get("Location")
    if loc is not None:
        assert not loc.startswith("//"), f"protocol-relative: {loc!r}"
        assert not loc.startswith("http"), f"absolute off-site: {loc!r}"
        assert "\\" not in loc, f"backslash in Location: {loc!r}"
        assert loc.startswith("/templates"), f"escaped prefix: {loc!r}"


def test_workflows_rest_normal_value_redirects(client):
    resp = client.get("/workflows/device-naming/script")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/templates/device-naming/script")
