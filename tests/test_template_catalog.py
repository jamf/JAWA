"""Guards on the bundled template catalog and its scripts.

Catalog-driven: every check iterates workflow_config.json, so a new
entry is covered automatically. ruff.toml excludes the bundled script
dir from repo linting (it is shipped content, not app code); these
tests apply the checks that actually matter there instead.
"""

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(
    REPO_ROOT, "data", "workflows", "workflow_config.json"
)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "data", "workflows", "scripts")


def _catalog():
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


CATALOG = _catalog()
SLUGS = [wf["slug"] for wf in CATALOG]


def _script_path(workflow):
    return os.path.join(SCRIPTS_DIR, workflow["script_file"])


def _script_source(workflow):
    with open(_script_path(workflow), "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(params=CATALOG, ids=SLUGS)
def workflow(request):
    return request.param


def test_script_file_exists(workflow):
    assert os.path.isfile(_script_path(workflow)), (
        f"{workflow['slug']} names a script_file that does not exist: "
        f"{workflow['script_file']}"
    )


def test_script_has_no_undefined_names(workflow):
    """F821/F401-clean: a script calling a function it never defines
    crashes with NameError on first trigger (bug B6). ruff.toml excludes
    this directory, so CI cannot catch it -- this test does.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            "F821,F401",
            "--output-format",
            "concise",
            _script_path(workflow),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{workflow['slug']} has undefined or unused names:\n"
        f"{result.stdout}{result.stderr}"
    )


def test_enrollment_pipeline_is_gone():
    """It shipped as a 6-stage outline with 7 undefined names and needed
    a CSV contract that exists nowhere in the repo. Cut in J16; this
    pins the decision so it cannot be restored unfinished.
    """
    assert "enrollment-pipeline" not in SLUGS
    assert not os.path.isfile(
        os.path.join(SCRIPTS_DIR, "enrollment_pipeline.py")
    )
