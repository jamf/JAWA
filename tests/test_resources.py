"""Resource file deletion edge cases (J5/B3)."""


def test_delete_with_no_file_selected_does_not_500(logged_in_client, jawa_env):
    # POST with no target_file query param — must not raise NameError/500.
    resp = logged_in_client.post("/resources/delete.html")
    assert resp.status_code < 500


def test_delete_nonexistent_file_does_not_500(logged_in_client, jawa_env):
    resp = logged_in_client.post(
        "/resources/delete.html?target_file=nope.txt"
    )
    assert resp.status_code < 500
