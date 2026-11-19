#!/usr/bin/env python3
"""Vendor wallrender from an EWOK checkout into data/workflows/lib.

wallrender lives in EWOK (github.com/ball42/enhanced-watermark-overlay-kit,
directory wallrender/). Brander imports this copy, so the preview EWOK
shows is the image a device receives. Never edit the copy by hand: the
lock file pins every file's SHA-256, and tests/test_wallrender_vendor.py
fails on any drift. To update, run from the JAWA repo root:

    python3 bin/vendor_wallrender.py ~/path/to/ewok origin/main

The copy is taken from the git ref, not the working tree, so the lock
records exactly which EWOK commit it came from.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(REPO_ROOT, "data", "workflows", "lib")
PACKAGE_DIR = os.path.join(LIB_DIR, "wallrender")
LOCK_PATH = os.path.join(LIB_DIR, "wallrender.lock.json")
SOURCE_PREFIX = "wallrender/wallrender/"
LICENSE_SOURCE = "wallrender/LICENSE"

# Pillow versions the deployed Brander accepts: JAWA's requirements.txt
# range. EWOK pins the same range, because text pixels differ between
# Pillow releases between minor releases, and the preview must
# be what a device gets. Change both repos together.
PILLOW_MIN = [13, 0]
PILLOW_BELOW = [14, 0]


def git(ewok, *args):
    return subprocess.run(
        ["git", "-C", ewok, *args], check=True, capture_output=True
    ).stdout


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ewok, ref = sys.argv[1], sys.argv[2]
    commit = git(ewok, "rev-parse", f"{ref}^{{commit}}").decode().strip()
    names = (
        git(ewok, "ls-tree", "-r", "--name-only", commit, SOURCE_PREFIX)
        .decode()
        .split()
    )
    names = [n for n in names if "__pycache__" not in n]
    pyproject = git(ewok, "show", f"{commit}:wallrender/pyproject.toml")
    version = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in pyproject.decode().splitlines()
        if line.startswith("version")
    )

    shutil.rmtree(PACKAGE_DIR, ignore_errors=True)
    files = {}
    sources = [(n, n[len(SOURCE_PREFIX) :]) for n in names]
    sources.append((LICENSE_SOURCE, "LICENSE"))
    for source, rel in sources:
        data = git(ewok, "show", f"{commit}:{source}")
        dest = os.path.join(PACKAGE_DIR, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as handle:
            handle.write(data)
        files[rel] = sha256(data)

    lock = {
        "package": "wallrender",
        "version": version,
        "source": "https://github.com/ball42/enhanced-watermark-overlay-kit",
        "commit": commit,
        "pillow_min": PILLOW_MIN,
        "pillow_below": PILLOW_BELOW,
        "files": dict(sorted(files.items())),
    }
    with open(LOCK_PATH, "w", encoding="utf-8") as handle:
        json.dump(lock, handle, indent=2)
        handle.write("\n")
    print(
        f"Vendored wallrender {version} from {commit[:12]}: "
        f"{len(files)} files."
    )


if __name__ == "__main__":
    main()
