"""Route sweep: every blueprint surface renders without a 500.

With TESTING enabled, unhandled exceptions propagate into the test
instead of rendering a 500 page, so a crashing route fails loudly
with its real traceback.
"""

import pytest

# (path, ) GET routes reachable with an authenticated session.
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
    "/automations/tap",
    "/automations/cron",
    "/automations/jamfpro/new",
    "/automations/okta/new",
    "/automations/custom/new",
    "/automations/tap/new",
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


def test_main_binds_loopback_by_default(jawa_env, monkeypatch):
    import app as jawa_app

    monkeypatch.delenv("JAWA_BIND", raising=False)
    calls = []
    monkeypatch.setattr(jawa_app, "serve", lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(jawa_app, "environment_setup", lambda d: None)
    monkeypatch.setattr(jawa_app, "register_blueprints", lambda: None)
    jawa_app.main()
    assert calls[0]["host"] == "127.0.0.1"

    monkeypatch.setenv("JAWA_BIND", "0.0.0.0")
    jawa_app.main()
    assert calls[1]["host"] == "0.0.0.0"


def test_healthz(client, jawa_env):
    before = sorted(p.name for p in jawa_env.data_dir.iterdir())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}

    jawa_env.webhooks_file.write_text("{not json")
    resp = client.get("/healthz")
    assert resp.status_code == 503
    assert "webhooks.json" in resp.get_data(as_text=True)
    assert sorted(p.name for p in jawa_env.data_dir.iterdir()) == before
    assert "Set-Cookie" not in resp.headers


def test_healthz_ok_on_fresh_install_without_stores(client, jawa_env):
    jawa_env.webhooks_file.unlink()
    jawa_env.cron_file.unlink()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert not jawa_env.webhooks_file.exists()


def test_healthz_reports_missing_scripts_dir(client, jawa_env):
    jawa_env.scripts_dir.rmdir()
    resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.get_json()["check"] == "scripts"


def test_log_page_returns_last_500_lines(logged_in_client, jawa_env):
    lines = [f"entry-{n:05d}" for n in range(1, 10001)]
    jawa_env.log_file.write_text("\n".join(lines) + "\n")
    body = logged_in_client.get("/log/view").get_data(as_text=True)
    assert "entry-09500" not in body
    positions = [body.index(f"entry-{n:05d}") for n in (9501, 9750, 10000)]
    assert positions == sorted(positions)
    import inspect

    from views import log_view

    assert "readlines" not in inspect.getsource(log_view._read_recent_logs)


def test_create_automation_page_lists_every_type(logged_in_client):
    from views._type_handlers import HANDLERS

    resp = logged_in_client.get("/automations/new")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert len(HANDLERS) == 5
    for tag, handler in HANDLERS.items():
        assert handler.display_name in body
        assert handler.summary and handler.summary in body
        assert f'href="/automations/{tag}/new"' in body


def test_dashboard_primary_button_opens_the_chooser(logged_in_client):
    import re

    body = logged_in_client.get("/dashboard").get_data(as_text=True)
    primary = re.search(
        r'<a href="([^"]*)" class="btn btn-hero-primary">([^<]*)</a>', body
    )
    assert primary.groups() == ("/automations/new", "Create automation")
