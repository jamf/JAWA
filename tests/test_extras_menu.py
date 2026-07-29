"""The Extras dropdown ships no dead links.

Two placeholders shipped disabled: Notebooks (no feature coming, so it
is removed) and Webhook Reference (now a real page).
"""


def test_notebooks_item_is_gone(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert "Notebooks" not in body


def test_webhook_reference_item_is_live(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert (
        '<a class="dropdown-item" href="/reference/webhooks">'
        "Webhook Reference</a>" in body
    )


def test_no_disabled_placeholder_items_remain(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    # The greyed-out placeholder pattern: a muted item pointing nowhere.
    assert 'class="dropdown-item text-muted" href="#"' not in body


def test_extras_still_links_log_and_files(logged_in_client, jawa_env):
    body = logged_in_client.get("/dashboard").data.decode()
    assert "/log/home.html" in body
    assert "/resources/files" in body
