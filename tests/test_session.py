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
    for bad in (0, 5, 999999, -10, "60", None, 61):
        assert jawa_app._resolve_session_timeout(
            {"session_timeout_minutes": bad}
        ) == 15
