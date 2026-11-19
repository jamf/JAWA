"""Tap action cooldown: one run per device per service per N minutes.

A person can reopen the web clip and tap again at any time, so without a
limit Brander could be made to send the same wallpaper over and over.
The limit is per service (cooldown_minutes, 0 = none) and per device,
claimed when a run starts so a double tap cannot slip through, and
released if the run fails so the person can retry straight away. An
admin can clear it from the service page.
"""

import json

import pytest

from bin import data_store
from webhook import tap_receiver
import subprocess

from tests.test_tap_receiver import (
    GOOD_QUERY,
    RecordingPopen,
    _make_service,
)


@pytest.fixture()
def fake_popen(monkeypatch):
    RecordingPopen.calls = []
    RecordingPopen.return_code = 0
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    return RecordingPopen


@pytest.fixture()
def clock(monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(tap_receiver, "_now", lambda: now["t"])
    return now


def _post(client, **overrides):
    return client.post("/tap/reset-ipad", data={**GOOD_QUERY, **overrides})


def test_second_run_inside_the_cooldown_is_refused(
    client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    assert _post(client).status_code == 200
    clock["t"] += 60
    resp = _post(client)
    assert resp.status_code == 429
    body = resp.get_data(as_text=True)
    assert "again in about 4 minutes" in body
    assert "Back to start" in body
    assert len(fake_popen.calls) == 1


def test_run_is_allowed_again_once_the_cooldown_passes(
    client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    clock["t"] += 5 * 60
    assert _post(client).status_code == 200
    assert len(fake_popen.calls) == 2


def test_the_cooldown_is_per_device(client, jawa_env, fake_popen, clock):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    other = _post(client, id="43", udid="OTHER-UDID")
    assert other.status_code == 200
    assert len(fake_popen.calls) == 2


def test_a_failed_run_does_not_start_the_cooldown(
    client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    fake_popen.return_code = 24
    assert _post(client).status_code == 500
    fake_popen.return_code = 0
    assert _post(client).status_code == 200
    assert len(fake_popen.calls) == 2


@pytest.mark.parametrize("setting", [{}, {"cooldown_minutes": 0}])
def test_no_cooldown_when_unset_or_zero(
    client, jawa_env, fake_popen, clock, setting
):
    _make_service(jawa_env, **setting)
    _post(client)
    assert _post(client).status_code == 200
    assert len(fake_popen.calls) == 2


def test_confirm_page_explains_the_wait_and_disables_the_button(
    client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    clock["t"] += 150
    body = client.get("/tap/reset-ipad", query_string=GOOD_QUERY).get_data(
        as_text=True
    )
    assert "again in about 3 minutes" in body
    assert "disabled data-cooldown" in body


def test_confirm_page_is_normal_without_a_recent_run(
    client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    body = client.get("/tap/reset-ipad", query_string=GOOD_QUERY).get_data(
        as_text=True
    )
    assert "disabled data-cooldown" not in body
    assert "again in" not in body


def test_last_minute_is_worded_plainly(client, jawa_env, fake_popen, clock):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    clock["t"] += 5 * 60 - 20
    assert "again in under a minute" in _post(client).get_data(as_text=True)


def test_claim_is_atomic(jawa_env):
    """A second claim before the first run finishes is refused, so two
    overlapping requests cannot both run."""
    assert data_store.claim_tap_run("svc", 42, 5, 100.0) == 0
    assert data_store.claim_tap_run("svc", 42, 5, 100.5) > 0


def test_cooldowns_survive_a_restart(jawa_env):
    data_store.claim_tap_run("svc", 42, 5, 100.0)
    stored = json.loads(open(data_store.COOLDOWNS_FILE).read())
    assert stored == {"svc": {"42": 100.0}}
    assert data_store.tap_cooldown_remaining("svc", 42, 5, 160.0) == 240


# --- admin override -------------------------------------------------------


def test_admin_can_reset_a_services_cooldowns(
    logged_in_client, client, jawa_env, fake_popen, clock
):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    resp = logged_in_client.post("/automations/tap/reset-ipad/reset-cooldowns")
    assert resp.status_code == 302
    assert _post(client).status_code == 200


def test_reset_needs_a_login(client, jawa_env, fake_popen, clock):
    _make_service(jawa_env, cooldown_minutes=5)
    _post(client)
    client.post("/automations/tap/reset-ipad/reset-cooldowns")
    assert _post(client).status_code == 429


def test_detail_page_shows_the_cooldown_and_the_reset_button(
    logged_in_client, jawa_env
):
    _make_service(jawa_env, cooldown_minutes=5)
    body = logged_in_client.get("/automations/tap/reset-ipad").get_data(
        as_text=True
    )
    assert "5 minutes" in body
    assert 'action="/automations/tap/reset-ipad/reset-cooldowns"' in body


# --- configuration --------------------------------------------------------


def test_edit_saves_the_cooldown(logged_in_client, jawa_env):
    entry = _make_service(jawa_env)
    form = {k: entry[k] for k in data_store_page_fields()}
    form.update(device_family="mobile", cooldown_minutes="7")
    logged_in_client.post("/automations/tap/reset-ipad/edit", data=form)
    saved = data_store.get_webhook_by_name("reset-ipad")
    assert saved["cooldown_minutes"] == 7


@pytest.mark.parametrize("value", ["-1", "abc", "1441", "2.5"])
def test_edit_rejects_a_bad_cooldown(logged_in_client, jawa_env, value):
    entry = _make_service(jawa_env, cooldown_minutes=5)
    form = {k: entry[k] for k in data_store_page_fields()}
    form.update(device_family="mobile", cooldown_minutes=value)
    logged_in_client.post("/automations/tap/reset-ipad/edit", data=form)
    assert (
        data_store.get_webhook_by_name("reset-ipad")["cooldown_minutes"] == 5
    )


def test_edit_form_shows_the_cooldown(logged_in_client, jawa_env):
    _make_service(jawa_env, cooldown_minutes=5)
    body = logged_in_client.get("/automations/tap/reset-ipad/edit").get_data(
        as_text=True
    )
    assert 'name="cooldown_minutes"' in body
    assert 'value="5"' in body


@pytest.mark.parametrize(
    "slug, expected",
    [("tap-brander", "5"), ("tap-return-to-service", "0")],
)
def test_catalog_sets_each_templates_default_cooldown(
    logged_in_client, jawa_env, slug, expected
):
    body = logged_in_client.get(f"/templates/{slug}/enable").get_data(
        as_text=True
    )
    assert 'name="cooldown_minutes"' in body
    assert f'value="{expected}"' in body


def data_store_page_fields():
    from views._type_handlers.tap_handler import PAGE_FIELDS

    return PAGE_FIELDS
