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
