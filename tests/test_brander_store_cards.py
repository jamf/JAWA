"""The Brander store shows each template as a card with a thumbnail, the
active version as a badge, and the preview picker by display name."""

import io

import pytest
from PIL import Image

from bin import brander_store as store
from tests.test_brander_store import TEMPLATE, package
from tests.test_brander_store_ui import upload


@pytest.fixture(autouse=True)
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "STORE_DIR", str(tmp_path / "brander_templates")
    )
    return tmp_path / "brander_templates"


def test_the_thumbnail_is_the_active_version_rendered_small(
    logged_in_client, jawa_env
):
    upload(logged_in_client, package())
    resp = logged_in_client.get("/brander/templates/ward-ipads/thumbnail.png")
    assert resp.status_code == 200 and resp.mimetype == "image/png"
    image = Image.open(io.BytesIO(resp.get_data()))
    assert max(image.size) <= 240
    # TEMPLATE is a navy background with a red logo: the render, not a placeholder.
    assert image.convert("RGB").getpixel((1, image.size[1] - 2)) == (
        0x0B,
        0x25,
        0x45,
    )


def test_the_thumbnail_follows_activation(logged_in_client, jawa_env):
    upload(logged_in_client, package())
    upload(
        logged_in_client,
        package(template=dict(TEMPLATE, background={"color": "#FFFFFF"})),
    )
    logged_in_client.post(
        "/brander/templates/ward-ipads/activate", data={"version": "2"}
    )
    image = Image.open(
        io.BytesIO(
            logged_in_client.get(
                "/brander/templates/ward-ipads/thumbnail.png"
            ).get_data()
        )
    )
    assert image.convert("RGB").getpixel((1, 1)) == (255, 255, 255)


def test_no_thumbnail_for_an_unknown_template(logged_in_client, jawa_env):
    assert (
        logged_in_client.get(
            "/brander/templates/nope/thumbnail.png"
        ).status_code
        == 404
    )


def test_the_thumbnail_needs_a_login(client, jawa_env):
    assert (
        client.get("/brander/templates/ward-ipads/thumbnail.png").status_code
        == 302
    )


def test_each_card_shows_its_thumbnail_and_an_active_badge(
    logged_in_client, jawa_env
):
    upload(logged_in_client, package())
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    assert 'class="rb-card brander-template"' in body
    assert 'src="/brander/templates/ward-ipads/thumbnail.png?v=1"' in body
    assert 'alt="Active version of Ward iPads on a sample device"' in body
    badge = body[body.index('class="rb-badge rb-badge--ok"') :]
    badge = badge[: badge.index("</span>")]
    assert "#circle-check" in badge and badge.endswith("Active")


def test_the_empty_store_is_an_empty_state_with_an_upload_button(
    logged_in_client, jawa_env
):
    body = logged_in_client.get("/brander/templates").get_data(as_text=True)
    empty = body[body.index('class="rb-empty"') :]
    assert 'class="rb-empty__icon"' in empty
    assert "No templates yet" in empty
    assert 'class="rb-empty__action"' in empty and 'name="package"' in empty
    assert ">Upload</button>" in empty


def test_the_preview_picker_shows_display_names(logged_in_client, jawa_env):
    upload(logged_in_client, package())
    body = logged_in_client.get("/brander/preview").get_data(as_text=True)
    assert (
        '<option value="store:ward-ipads" >Ward iPads (store)</option>' in body
    )
    assert ">Brander iPad (portrait and landscape) (shipped)</option>" in body
    assert ">example-ipad-template.json<" not in body
