"""Dashboard polish: styled empty-state CTAs, no inline styles.

The dashboard is the first screen after login, and with no automations
yet it is four empty states -- so those CTAs carry the first impression.
"""


def test_empty_state_cta_uses_the_brand_button(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    # No automations exist in a fresh temp env, so all four render.
    assert body.count('class="empty-state"') == 4
    assert body.count('class="btn btn-jawa btn-action"') == 4
    assert "Create one now" in body


def test_empty_state_has_no_inline_style(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert 'style="text-align: center; margin: 1rem auto;"' not in body


def test_empty_state_keeps_its_message_and_link(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert "No Jamf Pro webhooks to display." in body
    assert 'href="/automations/jamfpro/new"' in body
    assert 'href="/automations/cron/new"' in body


def test_empty_state_renders_on_a_type_list_page(
    logged_in_client, jawa_env
):
    # The macro is shared, so styling it fixes the list pages too.
    body = logged_in_client.get("/automations/okta").data.decode()
    assert 'class="empty-state"' in body
    assert 'class="btn btn-jawa btn-action"' in body
