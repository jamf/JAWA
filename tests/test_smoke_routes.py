"""Route sweep: every blueprint surface renders without a 500.

With TESTING enabled, unhandled exceptions propagate into the test
instead of rendering a 500 page, so a crashing route fails loudly
with its real traceback.
"""

import pytest

# (path, ) GET routes reachable with an authenticated session.
# /log/yield is deliberately absent: it is an infinite tail -f
# stream and would hang the test client.
AUTHED_ROUTES = [
    "/",
    "/home.html",
    "/login",
    "/dashboard",
    "/setup",
    "/cleanup",
    "/success",
    "/error",
    "/automations",
    "/automations/jamfpro",
    "/automations/okta",
    "/automations/custom",
    "/automations/cron",
    "/automations/jamfpro/new",
    "/automations/okta/new",
    "/automations/custom/new",
    "/automations/cron/new",
    "/templates",
    "/templates/device-naming",
    "/templates/device-naming/script",
    "/templates/import",
    "/reference/webhooks",
    "/reference/webhooks/ComputerAdded",
    "/setup/credentials",
    "/resources/files",
    "/branding",
    "/python",
    "/bash",
    "/search?q=test",
    "/api/search?q=test",
    "/log/home.html",
    "/log/view",
    "/log/download",
]

# Legacy URLs that must permanently redirect to /automations/*.
LEGACY_REDIRECTS = [
    ("/webhooks", "/automations"),
    ("/webhooks/jamf", "/automations/jamfpro"),
    ("/webhooks/okta", "/automations/okta"),
    ("/webhooks/custom", "/automations/custom"),
    ("/cron", "/automations/cron"),
]

# Routes that must not expose content to an anonymous client.
PROTECTED_ROUTES = [
    "/dashboard",
    "/setup",
    "/cleanup",
    "/automations",
    "/automations/jamfpro",
    "/templates",
    "/reference/webhooks",
    "/setup/credentials",
    "/resources/files",
    "/branding",
    "/log/home.html",
]


@pytest.mark.parametrize("path", AUTHED_ROUTES)
def test_authed_route_does_not_error(logged_in_client, path):
    resp = logged_in_client.get(path)
    assert resp.status_code < 500


@pytest.mark.parametrize("path,target", LEGACY_REDIRECTS)
def test_legacy_route_redirects(logged_in_client, path, target):
    resp = logged_in_client.get(path)
    assert resp.status_code == 301
    assert target in resp.headers["Location"]


@pytest.mark.parametrize("path", PROTECTED_ROUTES)
def test_protected_route_rejects_anonymous(client, path):
    resp = client.get(path)
    # Anonymous access must bounce to login/logout, never render.
    assert resp.status_code in (301, 302)


def test_unknown_automation_type_is_handled(logged_in_client):
    # abort(404) is intercepted by the custom 404 handler, which
    # sends signed-in users back to the dashboard.
    resp = logged_in_client.get("/automations/nosuchtype")
    assert resp.status_code in (301, 302)
    assert "/dashboard" in resp.headers["Location"]


def test_unknown_page_is_handled(logged_in_client):
    # Custom 404 handler redirects signed-in users to the dashboard.
    resp = logged_in_client.get("/definitely/not/a/page")
    assert resp.status_code in (301, 302)
    assert "/dashboard" in resp.headers["Location"]
