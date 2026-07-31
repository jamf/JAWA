"""The Webhook Reference pages are read-only docs behind auth.

Namespaced under /reference/ on purpose: /webhooks* is already taken by
the legacy automation redirects in app.py.
"""

import json
import re

import pytest

from bin.data_store import get_webhook_schemas

# The overview table is the only place an event link is wrapped in
# <code>; the sidebar renders bare anchors. Counting this shape keeps
# the assertions below pinned to the table rather than to the sidebar,
# which emits the same category headings and event names.
TABLE_EVENT_LINK = re.compile(r'<a href="/reference/webhooks/([^"]+)"><code>')


def _catalog_events():
    return [
        event
        for events in get_webhook_schemas()["categories"].values()
        for event in events
    ]


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
    # The headings and names above are also emitted by the sidebar, so
    # they cannot see the table at all. Descriptions and the standard
    # table treatment come only from the table.
    assert "new computer record is created" in body
    assert 'class="hippocrates"' in body


def test_overview_lists_every_catalog_event(logged_in_client, jawa_env):
    body = logged_in_client.get("/reference/webhooks").data.decode()
    events = _catalog_events()
    # A row per catalog event and no more: a count read off the page,
    # not a literal that has to be bumped when Jamf adds an event.
    assert TABLE_EVENT_LINK.findall(body) == events
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
    catalog = json.loads(jawa_env.webhook_schemas_file.read_text())
    catalog["schemas"] = []
    jawa_env.webhook_schemas_file.write_text(json.dumps(catalog))

    resp = logged_in_client.get("/reference/webhooks")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Computer Events" in body
    assert "ComputerAdded" in body


def test_overview_still_answers_when_one_events_entry_is_damaged(
    logged_in_client, jawa_env
):
    """One damaged entry must not take the whole index down.

    The overview looks up a description for every event it lists, so a
    single hand-edited entry is reachable here without anyone opening
    that event's page. The entry is present but is not a mapping, so it
    cannot answer the description lookup: the row must fall back to an
    empty description and the page must still list the event.
    """
    pristine = jawa_env.webhook_schemas_file.read_text()
    for shape in ("TBD", ["jssID", "udid"], 5):
        catalog = json.loads(pristine)
        catalog["schemas"]["ComputerAdded"] = shape
        jawa_env.webhook_schemas_file.write_text(json.dumps(catalog))

        resp = logged_in_client.get("/reference/webhooks")
        assert resp.status_code == 200, shape
        body = resp.data.decode()
        # The categories are a separate section and undamaged, so the
        # event is still listed and still linked.
        assert "Computer Events" in body, shape
        assert "/reference/webhooks/ComputerAdded" in body, shape
        # Undamaged siblings keep their descriptions.
        assert "computer checks in" in body, shape


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
    # Copy unique to the pending branch. The catalog description also
    # contains "pending confirmation", so asserting that phrase alone
    # would pass without the branch; this sentence exists only here, and
    # is what tells the reader the event is usable regardless.
    assert "it is selectable when you create a Jamf Pro" in body
    # A pending event still gets the section heading a normal event
    # gets, so the page does not look truncated...
    assert "Event schema" in body
    # ...but none of the machinery a documented event renders.
    assert 'class="hippocrates"' not in body
    assert 'id="example-json"' not in body
    assert "Sample payload" not in body


def test_detail_still_answers_when_one_events_entry_is_damaged(
    logged_in_client, jawa_env
):
    """A single malformed entry degrades that event, not the page.

    The accessor validates each catalog section as a whole and cannot
    see inside it, so a hand edit that damages one event leaves the key
    in place: the view does not treat the event as unknown, and the page
    is asked to render an entry whose field mapping may be missing or
    may not be a mapping at all. Every shape must render an empty field
    list rather than failing, because this file is hand-maintained.

    The wrong-typed mappings matter most: unlike an empty one they are
    truthy, so a guard that only tests falsiness lets them through to a
    lookup that fails.
    """
    pristine = jawa_env.webhook_schemas_file.read_text()
    shapes = (
        # The whole entry replaced by a scalar.
        "not an object",
        # Truthy, wrong-typed field mappings -- the plausible slips in a
        # hand-maintained mapping.
        {"description": "d", "schema": "TBD"},
        {"description": "d", "schema": ["jssID", "udid"]},
        {"description": "d", "schema": 5},
        # Falsy shapes, for completeness.
        {"description": "d", "schema": {}},
        {"description": "d"},
    )
    for shape in shapes:
        catalog = json.loads(pristine)
        catalog["schemas"]["ComputerAdded"] = shape
        jawa_env.webhook_schemas_file.write_text(json.dumps(catalog))

        resp = logged_in_client.get("/reference/webhooks/ComputerAdded")
        assert resp.status_code == 200, shape
        # The rest of the catalog is undamaged, so the sidebar still
        # lists the events and the heading still renders.
        body = resp.data.decode()
        assert "Event schema" in body, shape
        assert "/reference/webhooks/ComputerCheckIn" in body, shape
        # No field row survives the damage, whatever its shape. Scoped
        # to the table-row markup: the sample payload is a separate
        # catalog section, so it is undamaged and still names its
        # fields.
        assert "<td><code>jssID</code></td>" not in body, shape


@pytest.mark.parametrize(
    "bad_value",
    [
        "JSSStartup",  # string
        {"JSSStartup": "x"},  # mapping
    ],
    ids=["string", "mapping"],
)
def test_a_miscategorised_event_list_degrades_that_group_only(
    logged_in_client, jawa_env, bad_value
):
    """The overview applies the same shape rule as the event dropdown.

    A hand edit that leaves one category holding a bare string or a
    mapping instead of a list is iterable, so the page does not fail --
    it renders a row and a sidebar link per character or per key, every
    one of them linking to an event that does not exist. That group must
    be dropped instead.
    """
    jawa_env.webhook_schemas_file.write_text(
        json.dumps(
            {
                "categories": {
                    "Computer Events": ["ComputerAdded"],
                    "System Events": bad_value,
                },
                "schemas": {},
                "examples": {},
            }
        )
    )
    resp = logged_in_client.get("/reference/webhooks")
    assert resp.status_code == 200
    body = resp.data.decode()
    # The undamaged group still renders its table row.
    assert TABLE_EVENT_LINK.findall(body) == ["ComputerAdded"]
    # ...and the damaged one contributes nothing anywhere on the page:
    # no table row, no heading, and no per-character sidebar link. Kept
    # at document scope so a guard applied to only one of the two loops
    # cannot satisfy it.
    assert "System Events" not in body
    assert not [
        event
        for event in re.findall(r'/reference/webhooks/([^"]+)"', body)
        if len(event) == 1
    ]


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
