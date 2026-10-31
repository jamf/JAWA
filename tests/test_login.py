"""Console login flow against a fully faked Jamf Pro."""

import pytest
from datetime import datetime, timedelta, timezone



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


class NotJamfResponse:
    """A reachable non-Jamf endpoint: HTTP 200 whose body is not JSON.

    Any random website answers /JSSResource/activationcode with a 200
    HTML page and its token endpoint with non-JSON, so this stands in
    for `fiddlefaddle.com` and friends.
    """

    status_code = 200

    def json(self):
        raise ValueError("not JSON")

    def raise_for_status(self):
        pass


def test_logout_clears_token(logged_in_client):
    # A stale token surviving logout is the core of the bypass: a later
    # bogus login sees a truthy session["token"] and sails past the
    # credential gate. Logout must clear it.
    with logged_in_client.session_transaction() as sess:
        assert sess.get("token"), "fixture should have logged in with a token"
    logged_in_client.get("/logout")
    with logged_in_client.session_transaction() as sess:
        assert not sess.get("token"), "logout must clear the API token"


def test_stale_token_blocks_bogus_login(logged_in_client, monkeypatch):
    # THE BYPASS: reproduce a real prior Jamf login (logged_in_client has
    # a valid session token), then attempt login with bogus creds against
    # a non-Jamf URL that merely returns 200. Before the fix the stale
    # token let this reach the dashboard.
    import requests

    # Plant a stale token as if a prior real login left one behind, even
    # if logout were skipped.
    with logged_in_client.session_transaction() as sess:
        sess["token"] = "stale-token-from-prior-real-login"
        sess["expires"] = "2099-01-01T00:00:00.000+0000"

    monkeypatch.setattr(requests, "post", lambda *a, **k: NotJamfResponse())
    monkeypatch.setattr(requests, "get", lambda *a, **k: NotJamfResponse())

    resp = logged_in_client.post(
        "/login",
        data={
            "url": "https://fiddlefaddle.com",
            "username": "fjdsklj",
            "password": "fjdklsjl",
        },
    )
    assert resp.status_code == 302
    assert "/dashboard" not in resp.headers.get("Location", "")
    assert "/logout" in resp.headers.get("Location", "")


def test_verify_jamf_access_rejects_non_jamf_200(client, jawa_env, monkeypatch):
    # Defense in depth: even if a token were present, a 200 from a
    # non-Jamf site (body not the activationcode JSON shape) must not
    # count as Jamf access. Token endpoint returns a real-looking token
    # so the only thing standing between bogus creds and the dashboard
    # is the shape check in _verify_jamf_access.
    import json as _json
    import requests

    jawa_env.server_file.write_text(_json.dumps({"brand": "JAWA"}))

    class TokenButNotJamf:
        status_code = 200

        def __init__(self, kind):
            self.kind = kind

        def json(self):
            if self.kind == "token":
                return {"token": "looks-real", "expires":
                        "2099-01-01T00:00:00.000+0000"}
            raise ValueError("activationcode body is HTML, not JSON")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        requests, "post", lambda *a, **k: TokenButNotJamf("token")
    )
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: TokenButNotJamf("activationcode")
    )

    resp = client.post(
        "/login",
        data={
            "url": "https://fiddlefaddle.com",
            "username": "fjdsklj",
            "password": "fjdklsjl",
        },
    )
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


# ---- activationcode shape acceptance (login regression) ----
#
# The guard in _verify_jamf_access exists to stop a reachable non-Jamf
# host from counting as a successful login. It originally required a
# top-level "activation_code" key, which no live instance sends -- real
# Jamf Pro answers with "license_information" -- so it rejected genuine
# logins against genuine servers. The suite did not catch it because the
# fixture mocked the invented shape. These tests pin both real spellings
# and keep the non-Jamf rejection honest.


class _ShapedActivationCode:
    """Token endpoint plus an activationcode body of a chosen shape."""

    status_code = 200

    def __init__(self, kind, body=None):
        self.kind = kind
        self.body = body

    def json(self):
        if self.kind == "token":
            return {
                "token": "looks-real",
                "expires": "2099-01-01T00:00:00.000+0000",
            }
        return self.body

    def raise_for_status(self):
        pass


def _login_with_activationcode_body(client, jawa_env, monkeypatch, body):
    import json as _json

    import requests

    jawa_env.server_file.write_text(_json.dumps({"brand": "JAWA"}))
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: _ShapedActivationCode("token")
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _ShapedActivationCode("activationcode", body),
    )
    return client.post(
        "/login",
        data={
            "url": "https://jamf.example.test",
            "username": "admin",
            "password": "hunter2",
        },
    )


def test_login_accepts_license_information_shape(
    client, jawa_env, monkeypatch
):
    """The shape a live Jamf Pro actually returns must be accepted."""
    resp = _login_with_activationcode_body(
        client,
        jawa_env,
        monkeypatch,
        {
            "license_information": {
                "organization_name": "Shinra Electric Power Company",
                "code": "AAAA-BBBB-CCCC-DDDD",
            }
        },
    )
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers.get("Location", "")


def test_login_accepts_activation_code_shape(client, jawa_env, monkeypatch):
    """The other published spelling must be accepted too."""
    resp = _login_with_activationcode_body(
        client,
        jawa_env,
        monkeypatch,
        {"activation_code": {"organization_name": "Test Org"}},
    )
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers.get("Location", "")


def test_login_rejects_json_200_that_is_not_jamf(
    client, jawa_env, monkeypatch
):
    """A non-Jamf host answering valid JSON still must not log in.

    Tighter than the non-JSON case: this body parses fine and carries
    neither wrapper key, which is the only thing the guard keys off.
    """
    resp = _login_with_activationcode_body(
        client, jawa_env, monkeypatch, {"welcome": "to my blog"}
    )
    assert resp.status_code == 302
    assert "/dashboard" not in resp.headers.get("Location", "")
    assert "/logout" in resp.headers.get("Location", "")


# --- active_url must be one of the URLs this JAWA is configured for ---
#
# Both login gates query whatever host session["url"] names, so a host
# the caller chooses answers both of them: get_token() had no
# raise_for_status (any status with a JSON "token" passed) and
# _verify_jamf_access only checks the activationcode body's shape. The
# login page renders active_url as a two-option <select> over the
# configured URLs, so the UI presents the server as pinned -- but the
# resolver honoured any POSTed value. An allow-list here is what makes
# the downstream gates mean anything.


def _login_against(client, jawa_env, monkeypatch, active_url, configured):
    """POST /login with a chosen active_url against a Jamf-shaped host."""
    import json as _json

    import requests

    jawa_env.server_file.write_text(_json.dumps(configured))
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: _ShapedActivationCode("token")
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _ShapedActivationCode(
            "activationcode",
            {"license_information": {"organization_name": "Test Org"}},
        ),
    )
    return client.post(
        "/login",
        data={
            "active_url": active_url,
            "username": "admin",
            "password": "hunter2",
        },
    )


CONFIGURED = {
    "brand": "JAWA",
    "jps_url": "https://primary.jamfcloud.test",
    "alternate_jps": "https://alternate.jamfcloud.test",
}


@pytest.mark.parametrize(
    "hostile",
    [
        pytest.param("https://attacker.example", id="off-list-host"),
        pytest.param("http://127.0.0.1:8000", id="loopback"),
        pytest.param(
            "https://primary.jamfcloud.test.attacker.example",
            id="suffix-lookalike",
        ),
        pytest.param(
            "https://attacker.example#https://primary.jamfcloud.test",
            id="fragment-smuggle",
        ),
    ],
)
def test_login_refuses_an_unconfigured_active_url(
    client, jawa_env, monkeypatch, hostile
):
    """The attacker's host answers both gates Jamf-shaped and still fails.

    Both mocks here are deliberately cooperative -- they return exactly
    what a real Jamf Pro returns. That is the point: the shape checks
    cannot distinguish an attacker-chosen host, so only the allow-list
    can.
    """
    resp = _login_against(client, jawa_env, monkeypatch, hostile, CONFIGURED)
    with client.session_transaction() as sess:
        assert "username" not in sess, (
            f"logged in against {hostile!r}, which is not a configured "
            f"Jamf Pro URL"
        )
    location = resp.headers.get("Location", "")
    assert resp.status_code == 302
    assert "/dashboard" not in location
    assert "/logout" in location
    assert "Unrecognized+server" in location or "Unrecognized%20server" in location


@pytest.mark.parametrize(
    "allowed",
    [
        pytest.param("https://primary.jamfcloud.test", id="primary"),
        pytest.param("https://alternate.jamfcloud.test", id="alternate"),
        pytest.param("https://primary.jamfcloud.test/", id="trailing-slash"),
    ],
)
def test_login_still_accepts_a_configured_active_url(
    client, jawa_env, monkeypatch, allowed
):
    """The alternate-JPS feature must keep working, slash-insensitively."""
    resp = _login_against(client, jawa_env, monkeypatch, allowed, CONFIGURED)
    with client.session_transaction() as sess:
        assert sess.get("username") == "admin", (
            f"a configured URL ({allowed!r}) was refused"
        )
    assert "/dashboard" in resp.headers.get("Location", "")


def test_unconfigured_install_still_accepts_a_typed_url(
    client, jawa_env, monkeypatch
):
    """First-time setup has nothing to check against, so free text stands."""
    import json as _json

    import requests

    jawa_env.server_file.write_text(_json.dumps({"brand": "JAWA"}))
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: _ShapedActivationCode("token")
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _ShapedActivationCode(
            "activationcode", {"activation_code": {"code": "AAAA"}}
        ),
    )
    resp = client.post(
        "/login",
        data={
            "url": "https://fresh.jamfcloud.test",
            "username": "admin",
            "password": "hunter2",
        },
    )
    assert "/dashboard" in resp.headers.get("Location", "")


def _decode_session_cookie(client):
    """Decode the real signed session cookie the way a browser-side
    reader could: the payload is only signed, not encrypted."""
    import base64
    import zlib

    cookie = next(c for c in client._cookies.values() if c.key == "session")
    payload = cookie.value.split(".")
    compressed = cookie.value.startswith(".")
    segment = payload[1] if compressed else payload[0]
    raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    return (zlib.decompress(raw) if compressed else raw).decode()


def test_session_cookie_holds_no_password_or_basic_string(
    logged_in_client,
):
    import base64

    decoded = _decode_session_cookie(logged_in_client)
    basic = base64.b64encode(b"pytest-admin:hunter2").decode()
    assert "hunter2" not in decoded
    assert basic not in decoded
    assert "b64_auth" not in decoded
    assert '"password"' not in decoded
    with logged_in_client.session_transaction() as sess:
        assert "password" not in sess
        assert "b64_auth" not in sess
        assert sess["token"]


def test_login_refused_when_no_jamf_url_is_pinned(
    client, jawa_env, fake_jamf, monkeypatch
):
    monkeypatch.delenv("JAWA_ALLOW_UNPINNED_LOGIN", raising=False)
    jawa_env.server_file.write_text("{}")
    resp = client.post(
        "/login",
        data={
            "url": "https://attacker.example",
            "username": "u",
            "password": "p",
        },
    )
    assert "/dashboard" not in resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert "username" not in sess
    page = client.get(resp.headers["Location"], follow_redirects=True)
    assert b"Finish install: set the Jamf Pro URL" in page.data


def test_login_reports_a_jamf_timeout(client, jawa_env, monkeypatch):
    import requests

    def _stall(*_a, **_k):
        raise requests.exceptions.ReadTimeout("stalled")

    monkeypatch.setattr(requests, "post", _stall)
    resp = client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": "u",
              "password": "p"},
    )
    assert "/dashboard" not in resp.headers["Location"]
    page = client.get(resp.headers["Location"], follow_redirects=True)
    assert b"Connection Timeout" in page.data


def test_login_requests_all_carry_a_timeout(
    client, jawa_env, fake_jamf, monkeypatch
):
    import requests

    seen = []

    def _post(url, **kwargs):
        seen.append(kwargs.get("timeout"))
        return _orig_post(url, **kwargs)

    def _get(url, **kwargs):
        seen.append(kwargs.get("timeout"))
        return _orig_get(url, **kwargs)

    _orig_post, _orig_get = requests.post, requests.get
    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(requests, "get", _get)
    client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": "u",
              "password": "p"},
    )
    assert seen and all(t == 30 for t in seen)


def _expire_token(client, expires):
    with client.session_transaction() as sess:
        sess["token"] = "OLD"
        sess["expires"] = expires


def test_near_expiry_token_is_renewed_with_keep_alive(
    logged_in_client, jamf_fake_http, monkeypatch
):
    import requests

    Resp, default_post = jamf_fake_http
    calls = []

    def _post(url, **kwargs):
        if url.endswith("/api/v1/auth/keep-alive"):
            calls.append(kwargs)
            return Resp({"token": "RENEWED",
                         "expires": "2099-01-01T00:00:00.000+0000"})
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests, "post", _post)
    soon = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime(
        "%Y-%m-%dT%H:%M:%S.000%z"
    )
    _expire_token(logged_in_client, soon)
    from bin.tokens import fresh_token

    with logged_in_client:
        logged_in_client.get("/dashboard")
        from flask import session

        assert fresh_token() == "RENEWED"
        assert session["token"] == "RENEWED"
    assert calls[0]["headers"]["Authorization"] == "Bearer OLD"
    assert calls[0]["timeout"] == 30


def test_any_console_page_renews_a_token_with_ten_minutes_left(
    logged_in_client, jamf_fake_http, monkeypatch
):
    import requests

    Resp, default_post = jamf_fake_http

    def _post(url, **kwargs):
        if url.endswith("/api/v1/auth/keep-alive"):
            return Resp({"token": "RENEWED",
                         "expires": "2099-01-01T00:00:00.000+0000"})
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests, "post", _post)
    later = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.000%z"
    )
    _expire_token(logged_in_client, later)
    logged_in_client.get("/dashboard")
    with logged_in_client.session_transaction() as sess:
        assert sess["token"] == "RENEWED"


def test_expired_token_sends_admin_back_to_sign_in(
    logged_in_client, monkeypatch
):
    long_ago = "2000-01-01T00:00:00.000+0000"
    _expire_token(logged_in_client, long_ago)
    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data={"webhook_name": "x", "event": "ComputerAdded"},
    )
    assert resp.status_code == 302
    assert "/logout" in resp.headers["Location"]
    page = logged_in_client.get(resp.headers["Location"])
    assert b"Your Jamf Pro session ended. Sign in again." in page.data
    with logged_in_client.session_transaction() as sess:
        assert "token" not in sess


def test_failed_keep_alive_ends_the_session(
    logged_in_client, jamf_fake_http, monkeypatch
):
    import requests

    Resp, default_post = jamf_fake_http

    def _post(url, **kwargs):
        if url.endswith("/api/v1/auth/keep-alive"):
            return Resp({}, status_code=401)
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests, "post", _post)
    soon = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime(
        "%Y-%m-%dT%H:%M:%S.000%z"
    )
    _expire_token(logged_in_client, soon)
    resp = logged_in_client.post(
        "/automations/jamfpro/new",
        data={"webhook_name": "x", "event": "ComputerAdded"},
    )
    assert "/logout" in resp.headers["Location"]
    with logged_in_client.session_transaction() as sess:
        assert "token" not in sess


def _set_allowed_admins(jawa_env, names):
    import json
    data = json.loads(jawa_env.server_file.read_text())
    data["allowed_admins"] = names
    jawa_env.server_file.write_text(json.dumps(data))


def _sign_in(client, username):
    return client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": username,
              "password": "hunter2"},
    )


def test_login_refuses_users_outside_allowed_admins(
    client, jawa_env, fake_jamf
):
    _set_allowed_admins(jawa_env, ["alice"])
    resp = _sign_in(client, "bob")
    assert resp.status_code == 302
    assert "/logout" in resp.headers["Location"]
    assert client.get("/dashboard").status_code == 302
    with client.session_transaction() as sess:
        assert "username" not in sess

    resp = _sign_in(client, "Alice")
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]
    assert client.get("/dashboard").status_code == 200


def test_empty_allowed_admins_keeps_open_login(client, jawa_env, fake_jamf):
    resp = _sign_in(client, "anyone")
    assert "/dashboard" in resp.headers["Location"]


def test_setup_warns_when_allowed_admins_is_empty(logged_in_client):
    body = logged_in_client.get("/setup").data.decode()
    assert "Allowed admin accounts" in body
    assert "any Jamf Pro account that can sign in" in body


def test_setup_saves_allowed_admins_and_keeps_current_user(
    logged_in_client, jawa_env
):
    import json
    resp = logged_in_client.post(
        "/setup",
        data={"address": "https://jawa.example.test",
              "allowed_admins": "alice\nBob, carol"},
    )
    assert resp.status_code == 302
    saved = json.loads(jawa_env.server_file.read_text())["allowed_admins"]
    assert saved == ["alice", "Bob", "carol", "pytest-admin"]
    body = logged_in_client.get("/setup").data.decode()
    assert "any Jamf Pro account that can sign in" not in body


def _deny_tokens(monkeypatch, jamf_fake_http):
    import requests
    response_cls, default_post = jamf_fake_http

    def post(url, **kwargs):
        if url.endswith("/api/v1/auth/token"):
            return response_cls({}, status_code=401)
        return default_post(url, **kwargs)

    monkeypatch.setattr(requests, "post", post)


def test_failed_login_logs_client_address(
    client, jawa_env, fake_jamf, monkeypatch, jamf_fake_http
):
    import re
    _deny_tokens(monkeypatch, jamf_fake_http)
    resp = client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": "mallory",
              "password": "wrong"},
        headers={"X-Real-IP": "203.0.113.9"},
    )
    assert resp.status_code == 302
    lines = (jawa_env.data_dir / "jawa-auth.log").read_text().splitlines()
    assert len(lines) == 1
    assert re.fullmatch(
        r"\S+ \S+ - jawa\.auth - WARNING - "
        r"LOGIN FAILED user=mallory ip=203\.0\.113\.9",
        lines[0],
    )


def test_failed_login_log_line_cannot_be_forged_by_the_user_name(
    client, jawa_env, fake_jamf, monkeypatch, jamf_fake_http
):
    _deny_tokens(monkeypatch, jamf_fake_http)
    client.post(
        "/login",
        data={"url": "https://jamf.example.test",
              "username": "x ip=198.51.100.1\nLOGIN FAILED user=y",
              "password": "wrong"},
        headers={"X-Real-IP": "203.0.113.9"},
    )
    lines = (jawa_env.data_dir / "jawa-auth.log").read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].endswith(" ip=203.0.113.9")
    assert lines[0].count("LOGIN FAILED") == 1


def test_failed_login_falls_back_to_the_socket_address(
    client, jawa_env, fake_jamf, monkeypatch, jamf_fake_http
):
    _deny_tokens(monkeypatch, jamf_fake_http)
    client.post(
        "/login",
        data={"url": "https://jamf.example.test", "username": "u",
              "password": "wrong"},
    )
    line = (jawa_env.data_dir / "jawa-auth.log").read_text()
    assert " ip=127.0.0.1" in line


def test_successful_login_writes_no_failure_line(client, jawa_env, fake_jamf):
    _sign_in(client, "alice")
    assert not (jawa_env.data_dir / "jawa-auth.log").exists() or not (
        jawa_env.data_dir / "jawa-auth.log"
    ).read_text()
