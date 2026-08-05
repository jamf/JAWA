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


SCHEMAS_PATH = os.path.join(REPO_ROOT, "data", "webhook_schemas.json")


def _schemas():
    with open(SCHEMAS_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_trigger_event_is_real_or_explicitly_any(workflow):
    """A trigger_event that is not a Jamf event gets written verbatim
    into webhooks.json. "Any Event" and "MobileDeviceEnrolled /
    ComputerAdded" both shipped that way; null now means any-event.
    """
    event = workflow.get("trigger_event")
    if event is None:
        return
    valid = _schemas()["schemas"].keys()
    assert event in valid, (
        f"{workflow['slug']} declares trigger_event {event!r}, which is "
        f"not a key in webhook_schemas.json. Use null for any-event."
    )


def test_hook_name_is_legal_jamf_webhook_name(workflow):
    """JamfHandler.process_create rejects names containing a space, and
    the name is interpolated into the callback URL Jamf calls plus the
    webhook XML body.
    """
    hook_name = workflow["hook_name"]
    assert hook_name, f"{workflow['slug']} has an empty hook_name"
    assert " " not in hook_name, (
        f"{workflow['slug']} hook_name {hook_name!r} contains a space; "
        f"Jamf webhook names must be a single string"
    )
    for char in ("&", "<", ">", '"', "'", "/", "\\"):
        assert char not in hook_name, (
            f"{workflow['slug']} hook_name {hook_name!r} contains "
            f"{char!r}, which breaks the webhook XML or callback URL"
        )


def test_every_token_appears_exactly_once(workflow):
    """placeholder used to double as the replace-needle, so
    COOLDOWN_HOURS's needle "12" matched twice in its script. token is
    now explicit and must be unambiguous.
    """
    source = _script_source(workflow)
    for param in workflow.get("config_params", []):
        token = param["token"]
        count = source.count(token)
        assert count == 1, (
            f"{workflow['slug']} param {param['key']} token {token!r} "
            f"appears {count} times in {workflow['script_file']}; "
            f"expected exactly 1"
        )


def test_declared_exit_codes_match_the_script(workflow):
    import re

    source = _script_source(workflow)
    declared = {code["code"] for code in workflow.get("exit_codes", [])}
    actual = {
        int(match) for match in re.findall(r"sys\.exit\((\d+)\)", source)
    }
    actual.add(0)
    assert declared == actual, (
        f"{workflow['slug']} declares exit codes {sorted(declared)} but "
        f"the script uses {sorted(actual)}"
    )


def test_notebook_slug_is_gone(workflow):
    """Notebooks was removed from Extras in J14; the field had no
    consumers anywhere in the codebase.
    """
    assert "notebook_slug" not in workflow


def test_any_event_template_never_renders_the_word_none(
    logged_in_client, jawa_env
):
    """trigger_event is null for any-event templates. Jinja renders a
    bare None as the string "None", so every surface that shows the
    trigger must fall back to a real label instead.
    """
    slug = next(
        wf["slug"] for wf in CATALOG if wf.get("trigger_event") is None
    )
    for path in (
        "/templates",
        f"/templates/{slug}",
        f"/templates/{slug}/enable",
    ):
        body = logged_in_client.get(path).get_data(as_text=True)
        assert ">None<" not in body and "None\n" not in body, (
            f"{path} renders a literal None for a null trigger_event"
        )
        assert "Any Event" in body, (
            f"{path} does not label the null trigger_event as Any Event"
        )


def test_enabling_an_any_event_template_stores_no_none_event(
    logged_in_client, jawa_env
):
    """The stored event is compared against the inbound payload's
    webhookEvent, so persisting the string "None" would never match.
    """
    from bin import data_store

    slug = next(
        wf["slug"] for wf in CATALOG if wf.get("trigger_event") is None
    )
    logged_in_client.post(
        f"/templates/{slug}/enable", data={"webhook_name": "any-hook"}
    )
    entry = data_store.get_webhook_by_name("any-hook")
    assert entry is not None
    assert entry["event"] == ""


def test_script_survives_every_example_payload(workflow):
    """Both smart-group schemas set event.computer to a BOOLEAN, so the
    event.get("computer", {}).get(...) fallback pattern raised
    AttributeError (bug B15). Replay the catalog's own examples.
    """
    event = workflow.get("trigger_event")
    examples = _schemas()["examples"]
    payloads = list(examples.values()) if event is None else [examples[event]]
    source = _script_source(workflow)
    # Numeric tokens are written bare (no quotes) so the substituted
    # value is a real int; swap in a placeholder to make it parseable.
    for param in workflow.get("config_params", []):
        if param.get("type") == "number":
            source = source.replace(param["token"], "0")
    namespace = {}
    exec(compile(source, workflow["script_file"], "exec"), namespace)
    extract = namespace.get("_device_field")
    if extract is None:
        pytest.skip(f"{workflow['slug']} defines no _device_field")
    for payload in payloads:
        for key in ("deviceName", "serialNumber", "jssID"):
            extract(payload.get("event", {}), key, "Unknown")
