"""Dashboard polish: styled empty-state CTAs, no inline styles.

The dashboard is the first screen after login, and with no automations
yet it is four empty states -- so those CTAs carry the first impression.
"""

# A Jamf Pro URL crafted to break out of the href attribute and open a
# script tag, plus the entity-encoded form autoescaping must produce.
HOSTILE_URL = 'https://x.test/"><script>alert(1)</script>'
HOSTILE_URL_ENCODED = (
    "https://x.test/&#34;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
)


def _empty_states(body: str) -> str:
    """The empty-state markup only, hero section excluded.

    The hero links to /automations/jamfpro/new as well, so a
    whole-page assertion cannot tell an empty-state call to action
    from the hero's. An empty state holds no nested div, so its
    first closing tag ends it. Raises if the markup is absent
    rather than returning an empty string that asserts true.
    """
    opening = '<div class="empty-state">'
    start = body.index(opening)
    closing = "</div>"
    end = body.index(closing, body.rindex(opening)) + len(closing)
    return body[start:end]


def test_empty_state_cta_uses_the_brand_button(logged_in_client, jawa_env):
    states = _empty_states(logged_in_client.get("/dashboard").data.decode())
    # No automations exist in a fresh temp env, so all four render.
    assert states.count('class="empty-state"') == 4
    assert states.count('class="btn btn-jawa btn-action"') == 4
    assert "Create one now" in states


def test_empty_state_has_no_inline_style(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert 'style="text-align: center; margin: 1rem auto;"' not in body


def test_empty_state_keeps_its_message_and_link(logged_in_client, jawa_env):
    states = _empty_states(logged_in_client.get("/dashboard").data.decode())
    assert "No Jamf Pro webhooks to display." in states
    assert 'href="/automations/jamfpro/new"' in states
    assert 'href="/automations/cron/new"' in states


def test_empty_state_renders_on_a_type_list_page(
    logged_in_client, jawa_env
):
    # The macro is shared, so styling it fixes the list pages too.
    states = _empty_states(
        logged_in_client.get("/automations/okta").data.decode()
    )
    assert 'class="empty-state"' in states
    assert 'class="btn btn-jawa btn-action"' in states


def test_hero_subtitle_has_no_inline_style(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    # The JPS-URL link used to carry style='color: rgba(...)'.
    assert "style='color: rgba(255,255,255,0.9);'" not in body
    assert 'style="color: rgba(255,255,255,0.9);"' not in body


def test_hero_subtitle_still_links_the_jamf_pro_url(
    logged_in_client, jawa_env
):
    body = logged_in_client.get("/dashboard").data.decode()
    assert "webhooks" in body
    assert "timed automations" in body
    assert 'href="https://jamf.example.test"' in body
    assert 'target="_blank"' in body
    # New tab hygiene on an admin-supplied destination.
    assert 'rel="noopener"' in body
    # The anchor's visible text is the whole point of the link, and it
    # is the only thing the fallback expression produces -- no caller
    # passes explicit link text, so nothing else covers that branch.
    assert ">https://jamf.example.test</a>" in body


def test_hero_subtitle_link_is_attribute_escaped(logged_in_client, jawa_env):
    # The URL is rendered as an autoescaped attribute now, not spliced
    # into the |safe subtitle string.
    body = logged_in_client.get("/dashboard").data.decode()
    assert "<a href='" not in body


def test_hero_subtitle_escapes_a_hostile_jamf_pro_url(
    logged_in_client, jawa_env
):
    # The Jamf Pro URL is admin-supplied and lands in both an attribute
    # and the link text. A payload that closes the href and opens a tag
    # must come back entity-encoded, not as live markup: asserting only
    # that the anchor avoids single quotes would still pass if a future
    # edit re-concatenated it into the |safe subtitle with double ones.
    with logged_in_client.session_transaction() as sess:
        sess["url"] = HOSTILE_URL
    body = logged_in_client.get("/dashboard").data.decode()
    assert HOSTILE_URL_ENCODED in body
    assert HOSTILE_URL not in body
    assert '"><script>' not in body
    assert "<script>alert(1)</script>" not in body
