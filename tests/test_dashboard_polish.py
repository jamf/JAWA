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


def test_empty_dashboard_shows_one_start_here_card(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert body.count('class="start-here"') == 1
    assert "Start here" in body
    assert 'class="empty-state"' not in body
    assert "Create one now" not in body
    card = body[body.index('class="start-here"') :]
    card = card[: card.index("</div>")]
    assert card.count("<li>") == 4
    for kind in ("jamfpro", "okta", "custom", "cron"):
        assert f'href="/automations/{kind}/new"' in card
    assert card.count('class="btn btn-jawa btn-action"') == 1


def test_populated_dashboard_has_no_start_here_card(
    logged_in_client, jawa_env
):
    _seed_rows(jawa_env)
    body = logged_in_client.get("/dashboard").data.decode()
    assert "Start here" not in body
    assert 'class="start-here"' not in body


def test_empty_state_renders_on_a_type_list_page(logged_in_client, jawa_env):
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


def _seed_rows(jawa_env):
    jawa_env.add_webhook(
        {
            "name": "RenameOnEnroll",
            "tag": "jamfpro",
            "event": "MobileDeviceEnrolled",
            "description": "Renames new iPads to the asset tag",
            "script": "/x/rename.sh",
        }
    )
    jawa_env.add_webhook(
        {
            "name": "HelpdeskTicket",
            "tag": "custom",
            "description": "ticket hook",
            "script": "/x/ticket.sh",
        }
    )
    jawa_env.cron_file.write_text(
        '[{"name": "NightlyInventory", "frequency": "Every day at 2:00 AM",'
        ' "description": "", "script": "/x/n.sh"}]'
    )


def test_dashboard_rows_show_each_trigger(logged_in_client, jawa_env):
    _seed_rows(jawa_env)
    body = logged_in_client.get("/dashboard").data.decode()
    assert "MobileDeviceEnrolled" in body
    assert "/hooks/HelpdeskTicket" in body
    assert "Every day at 2:00 AM" in body
    assert "Renames new iPads to the asset tag" in body


def test_dashboard_row_is_one_link_to_the_detail_page(
    logged_in_client, jawa_env
):
    _seed_rows(jawa_env)
    body = logged_in_client.get("/dashboard").data.decode()
    row = body[body.index('<li class="automation-row">') :]
    row = row[: row.index("</li>")]
    assert row.count("<a ") == 1
    assert 'href="/automations/jamfpro/RenameOnEnroll"' in row
    assert "View</a>" not in body


def _css() -> str:
    with open("static/css/main.css", encoding="utf-8") as handle:
        return handle.read()


def test_css_has_a_focus_visible_rule_with_outline():
    css = _css()
    assert ":focus-visible {" in css
    start = css.index("/* ===== Keyboard focus")
    rule = css[start : css.index("/* ===== Buttons", start)]
    assert "outline: 2px solid var(--color-primary)" in rule
    assert "outline-offset: 2px" in rule


def test_body_keeps_navbar_offset_on_phones():
    css = _css()
    assert "padding-top: 56px;" in css
    assert "@media (max-width: 979px) {\n    body" not in css


def test_detail_buttons_wrap_on_phones(logged_in_client, jawa_env):
    jawa_env.add_webhook(
        {
            "name": "Hook",
            "tag": "custom",
            "description": "",
            "script": "/x/h.sh",
        }
    )
    body = logged_in_client.get("/automations/custom/Hook").data.decode()
    assert 'class="action-row mt-4"' in body
    css = _css()
    media = css[css.index("@media (max-width: 575px) {\n    .action-row") :]
    assert "flex-wrap: wrap" in media
    assert "min-width: 0" in media
    assert ".action-row .btn-danger" in media
