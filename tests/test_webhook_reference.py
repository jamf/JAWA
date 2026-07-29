"""The Webhook Reference pages are read-only docs behind auth.

Namespaced under /reference/ on purpose: /webhooks* is already taken by
the legacy automation redirects in app.py.
"""

import re


def test_overview_renders(logged_in_client, jawa_env):
    resp = logged_in_client.get("/reference/webhooks")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Webhook Reference" in body
    # Every category heading and a representative event are listed.
    assert "Computer Events" in body
    assert "Mobile Device Events" in body
    assert "System Events" in body
    assert "ComputerAdded" in body


def test_overview_lists_all_23_events(logged_in_client, jawa_env):
    from bin.data_store import get_webhook_schemas

    body = logged_in_client.get("/reference/webhooks").data.decode()
    events = [
        e
        for evs in get_webhook_schemas()["categories"].values()
        for e in evs
    ]
    assert len(events) == 23
    for event in events:
        assert f"/reference/webhooks/{event}" in body


def test_detail_renders_for_a_known_event(logged_in_client, jawa_env):
    resp = logged_in_client.get("/reference/webhooks/ComputerAdded")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "ComputerAdded" in body
    # The event's description is shown. The field-schema table and the
    # sample payload arrive with the full detail view, asserted there.
    assert "computer record is created" in body


def test_unknown_event_is_handled(logged_in_client, jawa_env):
    # abort(404) -> the branded handler sends signed-in users home.
    resp = logged_in_client.get("/reference/webhooks/NotAnEvent")
    assert resp.status_code in (301, 302)
    assert "/dashboard" in resp.headers["Location"]


def test_reference_requires_a_session(client, jawa_env):
    for path in (
        "/reference/webhooks",
        "/reference/webhooks/ComputerAdded",
    ):
        resp = client.get(path)
        assert resp.status_code in (301, 302)


def test_overview_survives_a_catalog_missing_its_schemas(
    logged_in_client, jawa_env
):
    """A half-damaged catalog degrades, it does not blow up.

    The accessor validates each section independently, so a hand edit
    that turns "schemas" into an array leaves the category lists fully
    populated while every description lookup comes back undefined. The
    overview must still render the event names it does know about.
    """
    import json

    catalog = json.loads(jawa_env.webhook_schemas_file.read_text())
    catalog["schemas"] = []
    jawa_env.webhook_schemas_file.write_text(json.dumps(catalog))

    resp = logged_in_client.get("/reference/webhooks")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Computer Events" in body
    assert "ComputerAdded" in body


def test_legacy_webhooks_redirect_is_untouched(logged_in_client, jawa_env):
    # The new namespace must not shadow the legacy automation redirect.
    resp = logged_in_client.get("/webhooks")
    assert resp.status_code == 301
    assert "/automations" in resp.headers["Location"]


def test_detail_shows_the_field_schema_table(logged_in_client, jawa_env):
    body = logged_in_client.get(
        "/reference/webhooks/ComputerAdded"
    ).data.decode()
    assert "Event schema" in body
    # Fields render in the standard table treatment, not a bare table.
    assert 'class="hippocrates"' in body
    assert "jssID" in body
    assert "Unique Jamf Pro computer record ID" in body


def test_detail_embeds_the_payload_as_json_not_markup(
    logged_in_client, jawa_env
):
    body = logged_in_client.get(
        "/reference/webhooks/ComputerAdded"
    ).data.decode()
    # Payload goes into JS via tojson and is written with textContent;
    # it is never interpolated into markup with |safe.
    assert 'id="example-json"' in body
    assert '"webhookEvent": "ComputerAdded"' in body
    assert "JSON.stringify" in body
    # The json language pack is not in the layout; this page loads it.
    assert "languages/json.min.js" in body
    # The layout's highlightAll() has already run by then.
    assert "hljs.highlightElement" in body


def test_detail_offers_a_copy_button(logged_in_client, jawa_env):
    body = logged_in_client.get(
        "/reference/webhooks/ComputerAdded"
    ).data.decode()
    assert 'class="copy-btn"' in body
    assert "clipboard.writeText" in body


def test_pending_event_says_so_instead_of_showing_empty_fields(
    logged_in_client, jawa_env
):
    body = logged_in_client.get(
        "/reference/webhooks/DeviceRateLimited"
    ).data.decode()
    assert "pending confirmation" in body
    # No empty schema table and no payload block for a pending event.
    assert 'class="hippocrates"' not in body
    assert 'id="example-json"' not in body


def test_detail_survives_a_catalog_missing_its_examples(
    logged_in_client, jawa_env
):
    """A detail page must degrade the same way the overview does.

    Each catalog section is validated independently, so a hand edit that
    turns "examples" into an array leaves the field schema intact while
    every payload lookup comes back missing. The page must drop the
    sample-payload block and still render the schema table rather than
    raising while the template evaluates the payload.
    """
    import json

    catalog = json.loads(jawa_env.webhook_schemas_file.read_text())
    catalog["examples"] = []
    jawa_env.webhook_schemas_file.write_text(json.dumps(catalog))

    resp = logged_in_client.get("/reference/webhooks/ComputerAdded")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "jssID" in body
    assert 'id="example-json"' not in body


def test_reference_pages_carry_no_inline_styles(logged_in_client, jawa_env):
    # The design system forbids inline style= and <style> blocks. The
    # only inline style the shared layout itself renders is on the
    # session-timeout modal's "seconds" caption; the reference pages
    # must add nothing to that set.
    layout_styles = {'style="font-size: 0.85rem;"'}
    for path in (
        "/reference/webhooks",
        "/reference/webhooks/ComputerAdded",
    ):
        body = logged_in_client.get(path).data.decode()
        found = set(re.findall(r"""style=["'][^"']*["']""", body))
        assert found <= layout_styles, found - layout_styles
        assert "<style" not in body
