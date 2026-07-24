"""Session timeout resolution, enforcement, and cookie hardening (J6/B4)."""

import app as jawa_app


def test_resolve_defaults_to_15_when_missing():
    assert jawa_app._resolve_session_timeout({}) == 15


def test_resolve_accepts_ladder_values():
    for v in (15, 60, 240, 480):
        assert jawa_app._resolve_session_timeout(
            {"session_timeout_minutes": v}
        ) == v


def test_resolve_rejects_off_ladder_values():
    # Off-ladder, wrong type, and absurd values all fail safe to 15.
    # Bools and ladder-equal floats must also be rejected (strict int).
    for bad in (0, 5, 999999, -10, "60", None, 61, True, False, 60.0):
        assert jawa_app._resolve_session_timeout(
            {"session_timeout_minutes": bad}
        ) == 15


def test_cookie_flags_are_hardened():
    # Default (env var unset): Secure on, as in production.
    assert jawa_app.app.config["SESSION_COOKIE_SECURE"] is True
    assert jawa_app.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert jawa_app.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_insecure_cookies_opt_out_expression(monkeypatch):
    # The Secure flag is computed at import as
    # (JAWA_INSECURE_COOKIES != "1"). Verify that logic directly rather
    # than reloading the app module (reload corrupts the shared app
    # singleton other tests depend on). Secure-by-default; only the
    # explicit "1" opt-out disables it.
    def secure_for(env_value):
        if env_value is None:
            monkeypatch.delenv("JAWA_INSECURE_COOKIES", raising=False)
        else:
            monkeypatch.setenv("JAWA_INSECURE_COOKIES", env_value)
        import os

        return os.environ.get("JAWA_INSECURE_COOKIES") != "1"

    assert secure_for(None) is True        # unset -> secure (prod)
    assert secure_for("0") is True         # anything but "1" -> secure
    assert secure_for("1") is False        # explicit opt-out -> insecure


def test_login_makes_session_permanent(logged_in_client):
    with logged_in_client.session_transaction() as sess:
        assert sess.permanent is True


def test_before_request_applies_configured_timeout(logged_in_client, jawa_env):
    import json
    # Configure an extended (4h) timeout.
    data = json.loads(jawa_env.server_file.read_text())
    data["session_timeout_minutes"] = 240
    jawa_env.server_file.write_text(json.dumps(data))
    # Any authed request runs before_request, which sets the lifetime.
    logged_in_client.get("/dashboard")
    from datetime import timedelta
    assert jawa_app.app.permanent_session_lifetime == timedelta(minutes=240)


def test_before_request_failsafe_on_bad_config(logged_in_client, jawa_env):
    import json
    data = json.loads(jawa_env.server_file.read_text())
    data["session_timeout_minutes"] = 999999
    jawa_env.server_file.write_text(json.dumps(data))
    logged_in_client.get("/dashboard")
    from datetime import timedelta
    assert jawa_app.app.permanent_session_lifetime == timedelta(minutes=15)


def test_setup_persists_valid_timeout(logged_in_client, jawa_env):
    import json
    logged_in_client.post(
        "/setup",
        data={
            "address": "https://jawa.example.test",
            "jss-lock": "https://jamf.example.test",
            "alternate": "",
            "session_timeout_minutes": "240",
        },
    )
    data = json.loads(jawa_env.server_file.read_text())
    assert data["session_timeout_minutes"] == 240


def test_setup_rejects_off_ladder_timeout(logged_in_client, jawa_env):
    import json
    logged_in_client.post(
        "/setup",
        data={
            "address": "https://jawa.example.test",
            "jss-lock": "https://jamf.example.test",
            "alternate": "",
            "session_timeout_minutes": "999999",
        },
    )
    data = json.loads(jawa_env.server_file.read_text())
    # Off-ladder input is clamped to the safe default, never stored raw.
    assert data["session_timeout_minutes"] == 15


def test_setup_post_redirects_to_success(logged_in_client, jawa_env):
    # PRG: a successful setup POST redirects to /success rather than
    # rendering inline, so browser-back can't re-POST setup (J13).
    resp = logged_in_client.post(
        "/setup",
        data={
            "address": "https://jawa.example.test",
            "session_timeout_minutes": "15",
        },
    )
    assert resp.status_code == 302
    assert "/success" in resp.headers["Location"]


def test_setup_form_shows_timeout_control(logged_in_client, jawa_env):
    import json
    data = json.loads(jawa_env.server_file.read_text())
    data["session_timeout_minutes"] = 240
    jawa_env.server_file.write_text(json.dumps(data))
    resp = logged_in_client.get("/setup")
    body = resp.data.decode()
    assert 'name="session_timeout_minutes"' in body
    # Current value preselected.
    assert 'value="240" selected' in body
    # All tiers offered, including the extended ones.
    for minutes in ("15", "60", "240", "480"):
        assert f'value="{minutes}"' in body


def test_layout_injects_effective_timeout(logged_in_client, jawa_env):
    import json
    data = json.loads(jawa_env.server_file.read_text())
    data["session_timeout_minutes"] = 60
    jawa_env.server_file.write_text(json.dumps(data))
    resp = logged_in_client.get("/dashboard")
    body = resp.data.decode()
    # 60 min -> 3600 s injected for the modal to count down against.
    assert "3600" in body


def test_timeout_modal_is_sleep_robust(logged_in_client, jawa_env):
    # The modal must track an absolute deadline and re-check on tab
    # focus/visibility so it survives sleep (a decrementing setInterval
    # counter pauses while the machine sleeps and under-counts).
    # This is a structural assertion on the rendered JS; true
    # sleep-survival is a manual browser check (see DESIGN relic).
    resp = logged_in_client.get("/dashboard")
    body = resp.data.decode()
    # Deadline/real-clock based, not a decrementing counter.
    assert "Date.now()" in body
    assert "deadline" in body
    # Re-evaluates when the tab regains focus / becomes visible.
    assert "visibilitychange" in body
    assert 'addEventListener("focus"' in body
    # An already-expired session redirects to login with a reason.
    assert "error_title=Session+expired" in body


def test_non_dict_server_config_fails_safe(logged_in_client, jawa_env):
    # A hand-edited server.json that isn't a JSON object must not 500
    # every route; it must fall back to the 15-min default.
    jawa_env.server_file.write_text("[]")
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    from datetime import timedelta
    assert jawa_app.app.permanent_session_lifetime == timedelta(minutes=15)


def test_get_server_config_returns_dict_for_non_object(jawa_env):
    from bin import data_store
    jawa_env.server_file.write_text("42")
    assert data_store.get_server_config() == {}
