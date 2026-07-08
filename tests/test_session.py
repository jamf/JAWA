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
    assert jawa_app.app.config["SESSION_COOKIE_SECURE"] is True
    assert jawa_app.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert jawa_app.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


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
