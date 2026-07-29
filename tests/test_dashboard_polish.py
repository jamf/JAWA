"""Dashboard polish: styled empty-state CTAs, no inline styles.

The dashboard is the first screen after login, and with no automations
yet it is four empty states -- so those CTAs carry the first impression.
"""


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
