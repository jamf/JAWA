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
