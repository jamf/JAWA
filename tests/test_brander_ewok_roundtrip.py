"""A template exported from EWOK renders through Brander with the exact
pixels EWOK previewed.

tests/fixtures/ewok-bundle is EWOK's "Download for Brander (.zip)" of the
square iPad example, unzipped, plus expected.png: EWOK's own render of it
(the vendored wallrender, Pillow 13, rendered on Linux) for the values Brander builds from this
device record. If this fails, EWOK's preview and the devices disagree:
check that both repos pin the same wallrender and Pillow.
"""

import io
import os

from PIL import Image

from tests.test_brander_templates import (  # noqa: F401 -- fixtures
    _fresh_wallrender,
    jamf,
    load_brander,
    run,
)

BUNDLE = os.path.join(os.path.dirname(__file__), "fixtures", "ewok-bundle")


def test_brander_matches_the_ewok_preview_pixel_for_pixel(jamf):  # noqa: F811
    module = load_brander(
        template_path=os.path.join(
            BUNDLE, "brander-ipad-portrait-and-landscape.json"
        )
    )
    module.ASSETS_DIR = BUNDLE
    assert run(module) == 0
    with (
        Image.open(io.BytesIO(jamf.sent_image())) as sent,
        Image.open(os.path.join(BUNDLE, "expected.png")) as expected,
    ):
        assert sent.size == expected.size
        assert (
            sent.convert("RGB").tobytes() == expected.convert("RGB").tobytes()
        )


def test_bundle_readme_names_the_template_file():
    with open(os.path.join(BUNDLE, "README.txt"), encoding="utf-8") as handle:
        assert "brander-ipad-portrait-and-landscape.json" in handle.read()
