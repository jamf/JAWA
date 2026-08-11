"""Resource Files page: destructive-action safety + design-system pass.

Two concerns, one page. The safety half is that Download (benign) and
Delete (destructive) used to sit flush against each other, same size, so
a misclick landed on the wrong one. The unification half is that this
page predated the design system and kept its own table, headings and a
duplicated confirmation card.
"""

import os
import re


def _row_for(body: str, filename: str) -> str:
    """The table row holding ``filename``.

    Row-scoped rather than page-scoped: the filename also appears in the
    radio's id and value attributes, so a whole-page assertion on a size
    or type string could pass while the cell that shows it is missing.
    """
    start = body.index(f'value="{filename}"')
    row_start = body.rindex("<tr", 0, start)
    row_end = body.index("</tr>", start) + len("</tr>")
    return body[row_start:row_end]


def _write(env, name: str, content: bytes = b"x") -> None:
    (env.files_dir / name).write_bytes(content)


def _page(body: str) -> str:
    """This page's own markup, layout chrome excluded.

    The shared layout carries a session-timeout modal with inline styles
    and a script that reads ``document.hidden``, so whole-document
    assertions about inline styling or hidden files answer questions
    about the layout instead of about this page.
    """
    start = body.index('<div class="main-content')
    return body[start : body.index("<footer>", start)]


# ----------------------------------------------------------------- item A


def test_download_and_delete_are_separated(logged_in_client, jawa_env):
    _write(jawa_env, "thing.txt")
    body = logged_in_client.get("/resources/files").data.decode()
    # The two submits share one flex row; the gap utility is what keeps a
    # destructive action from sitting flush against a benign one.
    actions = body[body.index('value="Download"') - 400 :]
    actions = actions[: actions.index("</form>")]
    assert "gap-3" in actions


def test_delete_asks_for_confirmation_through_the_shared_card(
    logged_in_client, jawa_env
):
    _write(jawa_env, "thing.txt")
    resp = logged_in_client.get(
        "/resources/delete.html?target_file=thing.txt"
    )
    body = resp.data.decode()
    # The shared delete_confirmation markup, not a hand-rolled copy.
    assert 'class="delete-card"' in body
    assert 'class="delete-item-name"' in body
    assert "This action cannot be undone." in body
    # Copy rule: the button names the noun, never "Confirm"/"OK".
    assert "Delete File" in body
    assert ">Confirm<" not in body
    # The shared default speaks of "associated data", which means nothing
    # for a file -- the real consequence is a script that breaks.
    assert "all associated data" not in body
    assert "Any automation script that reads it will start failing." in body


def test_confirmation_names_the_file_it_will_delete(
    logged_in_client, jawa_env
):
    _write(jawa_env, "payroll-export.csv")
    body = logged_in_client.get(
        "/resources/delete.html?target_file=payroll-export.csv"
    ).data.decode()
    named = body[body.index('class="delete-item-name"') :]
    named = named[: named.index("</div>")]
    assert "payroll-export.csv" in named


def test_the_confirmation_card_is_not_a_second_copy_of_the_macro():
    """The card markup exists twice today, style block and all.

    Asserting on the rendered page cannot catch this: a duplicate that
    renders identically passes every output assertion right up until
    someone edits one copy. So this reads the template.
    """
    with open("templates/resources/delete.html", encoding="utf-8") as f:
        source = f.read()
    assert "delete_confirmation" in source
    assert "<style>" not in source
    assert ".delete-card {" not in source


def test_confirmation_cancel_goes_to_the_files_list(
    logged_in_client, jawa_env
):
    _write(jawa_env, "thing.txt")
    body = logged_in_client.get(
        "/resources/delete.html?target_file=thing.txt"
    ).data.decode()
    actions = body[body.index('class="delete-actions"') :]
    actions = actions[: actions.index("</form>")]
    # A blind history.back() walks to the spent list form (the J13
    # lesson); this page knows where it came from, so it says so.
    assert 'href="/resources/files"' in actions
    assert "history.back()" not in actions


def test_confirming_actually_deletes_the_file(logged_in_client, jawa_env):
    _write(jawa_env, "doomed.txt")
    resp = logged_in_client.post(
        "/resources/delete.html?target_file=doomed.txt"
    )
    assert resp.status_code == 302
    assert not (jawa_env.files_dir / "doomed.txt").exists()


def test_the_confirmation_form_posts_to_the_delete_route(
    logged_in_client, jawa_env
):
    """The macro takes an explicit action; a wrong one silently no-ops.

    The delete route reads target_file from the query string, so the
    action has to carry it. Rendering the card correctly but posting
    somewhere that drops the filename would look identical and delete
    nothing.
    """
    _write(jawa_env, "thing.txt")
    body = logged_in_client.get(
        "/resources/delete.html?target_file=thing.txt"
    ).data.decode()
    form = body[body.index('class="delete-card"') :]
    action = re.search(r'<form method="POST" action="([^"]+)"', form)
    assert action, "confirmation card renders no POST form"
    assert "target_file=thing.txt" in action.group(1)
    assert "/resources/delete.html" in action.group(1)


# ----------------------------------------------------------------- item B


def test_uploaded_files_use_the_standard_table(logged_in_client, jawa_env):
    _write(jawa_env, "thing.txt")
    body = logged_in_client.get("/resources/files").data.decode()
    assert 'class="hippocrates"' in body
    assert '<table id="files_table" class="table">' not in body


def test_page_sections_use_section_headers(logged_in_client, jawa_env):
    _write(jawa_env, "thing.txt")
    body = logged_in_client.get("/resources/files").data.decode()
    # One hero, then section-headers for everything below it.
    assert body.count('class="section-header"') == 2
    assert '<h4 class="text-center mb-3">' not in body
    assert "Upload a file" in body
    assert "Uploaded files" in body


def test_files_directory_is_a_caption_not_a_code_block(
    logged_in_client, jawa_env
):
    body = logged_in_client.get("/resources/files").data.decode()
    # The path is a caption. The navy+mono treatment is for code and
    # logs, and a directory path is neither.
    assert "<pre><code>" not in body
    assert str(jawa_env.files_dir) in body


def test_file_rows_show_size_and_type(logged_in_client, jawa_env):
    _write(jawa_env, "notes.txt", b"y" * 2048)
    body = logged_in_client.get("/resources/files").data.decode()
    assert "<th>Size</th>" in body
    assert "<th>Type</th>" in body
    row = _row_for(body, "notes.txt")
    assert "2.0 KB" in row
    assert "TXT" in row


def test_a_file_with_no_extension_still_renders_a_type(
    logged_in_client, jawa_env
):
    _write(jawa_env, "README", b"hi")
    body = logged_in_client.get("/resources/files").data.decode()
    row = _row_for(body, "README")
    # A placeholder, not an empty cell: the Type column gets scanned
    # down, and a blank reads as "failed to load" rather than "none".
    assert "&#8212;" in row or "—" in row
    # And whatever it shows, never a Python None leaked into the UI.
    assert "None" not in row
    assert "2 B" in row


def test_files_are_listed_in_a_stable_order(
    logged_in_client, jawa_env, monkeypatch
):
    """Sorted by name, not by whatever order the filesystem hands back.

    The order is pinned to something unsorted on purpose -- APFS returns
    a small directory alphabetically already, so leaving it to the
    filesystem would let an unsorted implementation pass.
    """
    for name in ("charlie.txt", "alpha.txt", "bravo.txt"):
        _write(jawa_env, name)
    monkeypatch.setattr(
        os, "listdir", lambda _: ["charlie.txt", "alpha.txt", "bravo.txt"]
    )
    body = logged_in_client.get("/resources/files").data.decode()
    positions = [
        body.index(f'value="{name}"')
        for name in ("alpha.txt", "bravo.txt", "charlie.txt")
    ]
    assert positions == sorted(positions)


def test_hidden_files_are_never_listed(
    logged_in_client, jawa_env, monkeypatch
):
    """Two ADJACENT dotfiles: the list-mutating filter used to skip one.

    Removing from a list while iterating it shifts the next element past
    the cursor, so a dotfile immediately after another leaked into the
    page. The order has to be pinned rather than left to the filesystem
    -- APFS hands back creation order shuffled, so an unpatched version
    of this test passes or fails by luck and proves nothing either way.
    """
    _write(jawa_env, ".DS_Store")
    _write(jawa_env, ".hidden")
    _write(jawa_env, "visible.txt")
    monkeypatch.setattr(
        os, "listdir", lambda _: [".DS_Store", ".hidden", "visible.txt"]
    )
    page = _page(logged_in_client.get("/resources/files").data.decode())
    assert ".DS_Store" not in page
    assert ".hidden" not in page
    assert "visible.txt" in page


def test_empty_state_invites_an_upload(logged_in_client, jawa_env):
    body = logged_in_client.get("/resources/files").data.decode()
    assert 'class="empty-state"' in body
    # Never a bare "No items" -- and never a stale table header either.
    assert "<th>Size</th>" not in body


def test_the_page_carries_no_inline_styles(logged_in_client, jawa_env):
    _write(jawa_env, "thing.txt")
    page = _page(logged_in_client.get("/resources/files").data.decode())
    assert "style=" not in page


def test_a_hostile_filename_is_escaped_in_the_table(
    logged_in_client, jawa_env
):
    """Filenames reach the page in a radio value, an id and a cell.

    Uploads go through secure_filename, but anything already sitting in
    the directory (dropped in over SSH, restored from a backup) does
    not, so the template is the only thing standing between a crafted
    name and the DOM.
    """
    hostile = '<img src=x onerror=alert(1)>.txt'
    _write(jawa_env, hostile)
    body = logged_in_client.get("/resources/files").data.decode()
    assert "<img src=x onerror=alert(1)>" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body


# ------------------------------------------------------- size formatting


def test_format_size_boundaries():
    from views.resource_view import _format_size

    # Whole bytes below 1 KB: a 40-byte script must not read "0.0 KB".
    assert _format_size(0) == "0 B"
    assert _format_size(40) == "40 B"
    assert _format_size(1023) == "1023 B"
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(1536) == "1.5 KB"
    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(16 * 1024 * 1024) == "16.0 MB"
    assert _format_size(1024**3) == "1.0 GB"


def test_a_vanished_file_does_not_break_the_listing(
    logged_in_client, jawa_env, monkeypatch
):
    """os.listdir then stat is a race: a file can go between the two.

    Two admins, or an admin and a script, and the listing 500s on a
    stat of something that no longer exists.
    """
    _write(jawa_env, "here.txt")
    _write(jawa_env, "vanishing.txt")
    real_getsize = os.path.getsize

    def flaky_getsize(path):
        if path.endswith("vanishing.txt"):
            raise OSError("No such file or directory")
        return real_getsize(path)

    monkeypatch.setattr(os.path, "getsize", flaky_getsize)
    resp = logged_in_client.get("/resources/files")
    assert resp.status_code == 200
    page = _page(resp.data.decode())
    assert "here.txt" in page
    # Dropped, not degraded into a phantom row: offering Download and
    # Delete on a file that no longer exists is worse than omitting it.
    assert "vanishing.txt" not in page
