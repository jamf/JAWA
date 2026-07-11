"""Console login flow against a fully faked Jamf Pro."""


def test_successful_login_reaches_dashboard(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"dashboard" in resp.data.lower()


def test_blank_password_is_rejected(client, fake_jamf):
    resp = client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": "u",
              "password": ""},
    )
    assert resp.status_code == 302
    assert "/logout" in resp.headers["Location"]


def test_logout_clears_session(logged_in_client):
    logged_in_client.get("/logout")
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 302


def test_anonymous_home_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_login_error_surfaces_when_no_jps_configured(client, jawa_env):
    # server.json with no jps_url is the branch that dropped errors.
    import json
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))
    resp = client.get(
        "/logout?error_title=Authentication+error"
        "&error_message=Passwords+can%27t+be+blank"
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Authentication error" in body
    # logout() HTML-escapes the message before rendering, so the
    # apostrophe surfaces as its entity in the login page body.
    assert "Passwords can&#39;t be blank" in body


def test_failed_login_retains_username_and_url(client, jawa_env, fake_jamf):
    # The plain url input only renders when no jps_url is locked in
    # server.json, which is the scenario where retaining the typed URL
    # matters. The default fixture locks a jps_url, so clear it here.
    import json
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))
    resp = client.post(
        "/login",
        data={
            "url": "https://jamf.example.test",
            "username": "hojo",
            "password": "",  # blank password -> auth failure
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'value="hojo"' in body
    assert 'value="https://jamf.example.test"' in body
    # Password must never be echoed back into the page.
    assert 'type="password"' in body  # field still present
    # (no password value assertion -- it must not be retained at all)


def test_prev_url_not_reflected_without_error(client, jawa_env):
    # A bare GET with prev_url but NO failed-login error must NOT
    # pre-fill the JPS URL field (phishing pre-fill prevention).
    import json
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))
    resp = client.get("/?prev_url=https://evil-jamf.example&prev_username=admin")
    body = resp.data.decode()
    assert "https://evil-jamf.example" not in body
    assert 'value="admin"' not in body


def test_prev_url_not_reflected_via_logout_error_param(client, jawa_env):
    # The prior gate keyed on error_title, which is attacker-suppliable
    # via /logout query params. Confirm a crafted /logout link canNOT
    # pre-fill the JPS URL / username (no session flash present).
    import json
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))
    resp = client.get(
        "/logout?error_title=x&prev_url=https://evil-jamf.example"
        "&prev_username=admin",
        follow_redirects=True,
    )
    body = resp.data.decode()
    assert "https://evil-jamf.example" not in body
    assert 'value="admin"' not in body


def test_login_fails_against_non_jamf_url(client, jawa_env, monkeypatch):
    # Regression guard for the 3.0.2 report where server.json pointing
    # at JAWA's own URL let any creds log in. A URL that does not answer
    # Jamf's token endpoint like Jamf Pro (returns non-JSON) must not
    # log in. Invert the conftest fake_jamf fixture: the token endpoint
    # returns a 200 whose .json() raises, so get_token() swallows the
    # error and never sets session["token"] -> _validate_credentials
    # bounces to /logout.
    import requests

    class NotJamfResponse:
        """A non-Jamf endpoint: HTTP 200 but the body is not JSON."""

        status_code = 200

        def json(self):
            raise ValueError("not JSON")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "post", lambda *a, **k: NotJamfResponse())
    monkeypatch.setattr(requests, "get", lambda *a, **k: NotJamfResponse())

    resp = client.post(
        "/login",
        data={
            "url": "https://not-jamf.example",
            "username": "u",
            "password": "p",  # non-blank, so the blank-password gate passes
        },
    )
    # Must NOT reach the dashboard; token fetch failed, so login bounces
    # to /logout with the "Could not fetch token" error.
    assert resp.status_code == 302
    assert "/dashboard" not in resp.headers.get("Location", "")
    assert "/logout" in resp.headers.get("Location", "")


def test_failed_login_does_not_reflect_script_injection(
    client, jawa_env, fake_jamf
):
    import json
    jawa_env.server_file.write_text(json.dumps({"brand": "JAWA"}))
    resp = client.post(
        "/login",
        data={
            "url": "https://jamf.example.test",
            "username": "<script>alert(1)</script>",
            "password": "",
        },
        follow_redirects=True,
    )
    body = resp.data.decode()
    # Autoescaped -- the raw tag must not appear unescaped in the body.
    assert "<script>alert(1)</script>" not in body
