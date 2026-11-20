"""The vendored wallrender must be exactly the EWOK commit it names.

Brander renders templates with data/workflows/lib/wallrender, a copy of
the renderer EWOK previews with. A hand edit here would make devices
receive something other than the preview, so every file is pinned by
SHA-256 in wallrender.lock.json. Update with bin/vendor_wallrender.py,
never by hand.
"""

import hashlib
import json
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(REPO_ROOT, "data", "workflows", "lib")
PACKAGE_DIR = os.path.join(LIB_DIR, "wallrender")

with open(
    os.path.join(LIB_DIR, "wallrender.lock.json"), encoding="utf-8"
) as _handle:
    LOCK = json.load(_handle)


def _vendored_files():
    found = set()
    for root, dirs, files in os.walk(PACKAGE_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            path = os.path.join(root, name)
            found.add(os.path.relpath(path, PACKAGE_DIR).replace(os.sep, "/"))
    return found


def test_lock_names_a_full_ewok_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", LOCK["commit"])
    assert LOCK["package"] == "wallrender"


def test_every_vendored_file_matches_its_pinned_hash():
    for rel, expected in LOCK["files"].items():
        with open(os.path.join(PACKAGE_DIR, rel), "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        assert actual == expected, f"{rel} drifted from the EWOK copy"


def test_no_unpinned_files_in_the_vendored_copy():
    assert _vendored_files() == set(LOCK["files"])


def test_pillow_range_matches_requirements():
    with open(
        os.path.join(REPO_ROOT, "requirements.txt"), encoding="utf-8"
    ) as handle:
        line = next(
            ln for ln in handle if ln.lower().startswith("pillow")
        ).strip()
    low = ".".join(str(n) for n in LOCK["pillow_min"])
    high = LOCK["pillow_below"][0]
    assert line.lower() == f"pillow>={low},<{high}"


def test_vendored_copy_imports_and_renders(monkeypatch):
    monkeypatch.syspath_prepend(LIB_DIR)
    for name in [m for m in sys.modules if m.startswith("wallrender")]:
        monkeypatch.delitem(sys.modules, name)
    import wallrender

    assert wallrender.__version__ == LOCK["version"]
    image = wallrender.render(
        {
            "schema_version": 1,
            "canvas": {"width": 60, "height": 120},
            "background": {"color": "#102030"},
            "layers": [
                {
                    "type": "text",
                    "text": "{{device_name}}",
                    "box": {"x": 0, "y": 0.4, "w": 1, "h": 0.2},
                    "size": 0.1,
                }
            ],
        },
        {"device_name": "iPad"},
        {}.__getitem__,
    )
    assert image.size == (60, 120)
    assert image.mode == "RGB"


@pytest.mark.parametrize("rel", ["LICENSE", "fonts/OFL.txt"])
def test_licences_ship_with_the_copy(rel):
    assert rel in LOCK["files"]
