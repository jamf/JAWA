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
    logged_in_client, jawa_env, enable_form
):
    """The stored event is compared against the inbound payload's
    webhookEvent, so persisting the string "None" would never match.
    """
    from bin import data_store

    slug = next(
        wf["slug"] for wf in CATALOG if wf.get("trigger_event") is None
    )
    logged_in_client.post(
        f"/templates/{slug}/enable",
        data=enable_form(slug, webhook_name="any-hook"),
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


ADVERSARIAL_VALUES = [
    # Power Automate / Logic Apps URL: the & runs got HTML-escaped to
    # &amp; and baked in corrupted (bug B13).
    "https://x.logic.azure.com:443/workflows/a/triggers/manual/paths/"
    "invoke?api-version=2016-06-01&sp=%2Ftriggers%2Frun&sig=AbC123",
    'secret"with"double-quotes',
    "secret'with'single-quotes",
    "trailing-backslash\\",
    "<script>alert(1)</script>",
    "amp & ersand",
    "new\nline",
]


@pytest.mark.parametrize("value", ADVERSARIAL_VALUES)
def test_substituted_value_survives_byte_exact(value):
    """The old engine ran HTML escape() over values before replacing
    them into PYTHON SOURCE, so any & " ' < > was corrupted. The
    generated script must still compile AND hold the exact input.
    """
    from views import template_view

    workflow = {
        "config_params": [
            {
                "key": "TEAMS_WEBHOOK_URL",
                "token": '"__JAWA_TEAMS_WEBHOOK_URL__"',
                "type": "text",
            }
        ]
    }
    source = 'TEAMS_WEBHOOK_URL = "__JAWA_TEAMS_WEBHOOK_URL__"\n'
    result = template_view.substitute_params(
        source, workflow, {"TEAMS_WEBHOOK_URL": value}, [], ""
    )
    namespace = {}
    exec(compile(result, "generated.py", "exec"), namespace)
    assert namespace["TEAMS_WEBHOOK_URL"] == value


def test_numeric_param_substitutes_a_real_int():
    from views import template_view

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    result = template_view.substitute_params(
        "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
        workflow,
        {"COOLDOWN_HOURS": "24"},
        [],
        "",
    )
    namespace = {}
    exec(compile(result, "generated.py", "exec"), namespace)
    assert namespace["COOLDOWN_HOURS"] == 24


def test_non_numeric_value_for_numeric_param_is_rejected():
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
            workflow,
            {"COOLDOWN_HOURS": "not-a-number"},
            [],
            "",
        )


def test_unfilled_param_fails_loud():
    """An unfilled field used to leave the placeholder baked in, so the
    automation misbehaved at trigger time instead of failing at enable.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "DB_PATH",
                "label": "SQLite Database Path",
                "token": '"__JAWA_DB_PATH__"',
                "type": "text",
            }
        ]
    }
    with pytest.raises(AutomationError) as excinfo:
        template_view.substitute_params(
            'DB_PATH = "__JAWA_DB_PATH__"\n', workflow, {}, [], ""
        )
    assert "SQLite Database Path" in excinfo.value.message


def test_credential_set_fills_the_standard_three():
    from views import template_view

    workflow = {
        "config_params": [
            {
                "key": "server_url",
                "token": '"__JAWA_SERVER_URL__"',
                "type": "text",
            },
            {
                "key": "client_id",
                "token": '"__JAWA_CLIENT_ID__"',
                "type": "text",
            },
            {
                "key": "client_secret",
                "token": '"__JAWA_CLIENT_SECRET__"',
                "type": "password",
            },
        ]
    }
    source = (
        'server_url = "__JAWA_SERVER_URL__"\n'
        'client_id = "__JAWA_CLIENT_ID__"\n'
        'client_secret = "__JAWA_CLIENT_SECRET__"\n'
    )
    credentials = [
        {
            "name": "prod",
            "server_url": "https://prod.jamfcloud.com",
            "client_id": "abc",
            # A quote in a saved secret used to break the generated
            # Python: the credential path did NOT escape.
            "client_secret": 'sh"h',
        }
    ]
    result = template_view.substitute_params(
        source, workflow, {}, credentials, "0"
    )
    namespace = {}
    exec(compile(result, "generated.py", "exec"), namespace)
    assert namespace["client_secret"] == 'sh"h'
    assert namespace["server_url"] == "https://prod.jamfcloud.com"


def _raw_workflow():
    return {
        "config_params": [
            {
                "key": "wifi_ssid",
                "label": "WiFi SSID",
                "token": "__JAWA_WIFI_SSID__",
                "raw": True,
                "type": "text",
            }
        ]
    }


# The one raw token in the catalog sits inside an XML <string> element
# held in a b"""...""" bytes literal, so it is neither quoted Python nor
# escaped XML. Each of these would produce a script that fails to
# compile or an Apple profile that is not well-formed XML.
RAW_REJECTED_VALUES = [
    'quote"breaks-the-bytes-literal',
    "apostrophe'in-xml",
    "angle<bracket",
    "angle>bracket",
    "back\\slash",
    "new\nline",
    # A bare & is not well-formed XML: the profile is rejected at
    # runtime, long after enable succeeded.
    "Corp & Guest",
    # A bytes literal cannot hold a non-ASCII character at all.
    "Café-WiFi",
]


@pytest.mark.parametrize("value", RAW_REJECTED_VALUES)
def test_raw_param_rejects_values_that_break_its_context(value):
    from views import template_view
    from views._type_handlers.base import AutomationError

    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "<key>SSID_STR</key><string>__JAWA_WIFI_SSID__</string>",
            _raw_workflow(),
            {"wifi_ssid": value},
            [],
            "",
        )


def test_raw_param_accepts_a_normal_ssid_and_stays_well_formed_xml():
    import xml.etree.ElementTree as ET

    from views import template_view

    result = template_view.substitute_params(
        "<string>__JAWA_WIFI_SSID__</string>",
        _raw_workflow(),
        {"wifi_ssid": "Corporate-WiFi 5GHz"},
        [],
        "",
    )
    assert ET.fromstring(result).text == "Corporate-WiFi 5GHz"


def test_raw_substitution_keeps_the_real_script_compiling():
    """The raw token lives in return_to_service.py inside a bytes
    literal, so a substituted value has to leave the whole module
    compilable -- not just the one line.
    """
    import xml.etree.ElementTree as ET

    from views import template_view

    workflow = next(
        wf
        for wf in CATALOG
        if any(param.get("raw") for param in wf.get("config_params", []))
    )
    form = {
        param["key"]: (
            "12"
            if param.get("type") == "number"
            else "Corporate-WiFi"
            if param.get("raw")
            else f"value-for-{param['key']}"
        )
        for param in workflow["config_params"]
    }
    result = template_view.substitute_params(
        _script_source(workflow), workflow, form, [], ""
    )
    assert "__JAWA_" not in result
    namespace = {}
    exec(compile(result, workflow["script_file"], "exec"), namespace)
    assert ET.fromstring(namespace["WIFI_PAYLOAD"]) is not None


def test_numeric_param_cannot_smuggle_code_into_a_bare_token():
    """markupsafe.escape() never protected this position: a payload with
    no quote or angle characters passed through it untouched, and the
    numeric token is written bare, so it landed in an expression
    position. Validation, not escaping, is what closes it.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "label": "Cooldown Hours",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    payload = "0 or exec(chr(112)+chr(97)+chr(115)+chr(115))"
    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__  # noqa: F821\n",
            workflow,
            {"COOLDOWN_HOURS": payload},
            [],
            "",
        )


def test_numeric_substitution_preserves_the_trailing_noqa_comment():
    """The noqa sits outside the token, so a plain string replace keeps
    it. Stripping or relocating it would reintroduce the F821 that
    test_script_has_no_undefined_names guards.
    """
    from views import template_view

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    result = template_view.substitute_params(
        "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__  # noqa: F821\n",
        workflow,
        {"COOLDOWN_HOURS": "12"},
        [],
        "",
    )
    assert result == "COOLDOWN_HOURS = 12  # noqa: F821\n"


def test_no_html_escaping_survives_in_the_substitution_path():
    """markupsafe.escape() belongs to the HTML surfaces (escape(slug)),
    never to Python source generation. Pin that separation so the
    corrupting call cannot be reintroduced into the engine.
    """
    import ast
    import inspect

    from views import template_view

    for func in (
        template_view.substitute_params,
        template_view._python_literal,
        template_view._numeric_literal,
        template_view._raw_literal,
    ):
        tree = ast.parse(inspect.getsource(func))
        called = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Bare escape(...) and dotted markupsafe.escape(...) both
            # have to be caught; matching only ast.Name let the dotted
            # form through.
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                prefix = getattr(node.func.value, "id", "")
                called.add(
                    f"{prefix}.{node.func.attr}" if prefix else node.func.attr
                )
        # re.escape is regex quoting of our OWN token needles, which is
        # required and safe. Only HTML escaping of a value is the bug.
        html_escapes = {
            name
            for name in called
            if name.split(".")[-1] == "escape" and name != "re.escape"
        }
        assert not html_escapes, (
            f"{func.__name__} HTML-escapes a value on its way into "
            f"Python source (bug B13): {sorted(html_escapes)}"
        )


def _assign_nodes(source):
    """Map every assigned name in `source` to its value AST node."""
    import ast

    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            found[target.id] = node.value
        elif isinstance(target, ast.Attribute):
            found[target.attr] = node.value
    return found


def test_one_params_value_cannot_break_out_via_a_later_token():
    """CRITICAL regression. Substitution used to apply one str.replace
    per param against a shared accumulator, so text a previous param had
    already substituted got re-scanned. A value carrying a LATER param's
    needle was therefore rewritten from the inside, breaking out of the
    Python string literal it was supposed to be trapped in and turning a
    config field into arbitrary code in the deployed script:

        self.server_url = 'x'+__import__("os").system(...)+'y'

    Single-value round-trip tests cannot see this -- it needs two params
    interacting -- which is why it shipped.
    """
    import ast

    from views import template_view

    # Synthetic tokens without the __JAWA_ prefix, so the belt-and-
    # braces prefix check cannot fire: this pins the single-pass
    # property itself, not the secondary guard.
    workflow = {
        "config_params": [
            {"key": "FIRST", "token": '"@@FIRST@@"', "type": "text"},
            {"key": "SECOND", "token": '"@@SECOND@@"', "type": "text"},
        ]
    }
    first = 'x"@@SECOND@@"y'
    second = '+__import__("os").system("echo PWNED")+'
    result = template_view.substitute_params(
        'FIRST = "@@FIRST@@"\nSECOND = "@@SECOND@@"\n',
        workflow,
        {"FIRST": first, "SECOND": second},
        [],
        "",
    )

    # Byte-exact survival...
    namespace = {}
    exec(compile(result, "generated.py", "exec"), namespace)
    assert namespace["FIRST"] == first
    assert namespace["SECOND"] == second
    # ...and structurally a plain string constant, not an expression.
    # Without this the value could still evaluate equal while having
    # executed something on the way.
    nodes = _assign_nodes(result)
    assert isinstance(nodes["FIRST"], ast.Constant), (
        f"FIRST became a {type(nodes['FIRST']).__name__}, not a string "
        f"constant: the value broke out of its literal"
    )
    assert nodes["FIRST"].value == first


def test_value_carrying_a_real_jawa_token_is_rejected(logged_in_client):
    """Belt and braces over the single pass: a submitted value that
    contains a real __JAWA_ needle is refused outright rather than
    relying on pass ordering to stay harmless.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = next(wf for wf in CATALOG if wf["slug"] == "device-naming")
    form = {
        "server_url": 'x"__JAWA_CLIENT_ID__"y',
        "client_id": '+__import__("os").system("echo PWNED")+',
        "client_secret": "s3cret",
    }
    with pytest.raises(AutomationError):
        template_view.substitute_params(
            _script_source(workflow), workflow, form, [], ""
        )


def test_the_reviewers_poc_does_not_execute_through_the_route(
    logged_in_client, jawa_env, enable_form
):
    """End-to-end through the real HTTP route: the PoC POST must not
    leave behind a deployed script that executes anything. Previously
    this returned 302, registered the webhook, and ran the payload when
    the receiver instantiated Config().
    """
    import ast

    marker = os.path.join(str(jawa_env.root), "pwned.txt")
    payload = f'+__import__("os").system("touch {marker}")+'
    try:
        logged_in_client.post(
            "/templates/device-naming/enable",
            data=enable_form(
                "device-naming",
                webhook_name="poc-hook",
                server_url='x"__JAWA_CLIENT_ID__"y',
                client_id=payload,
            ),
        )
    except Exception:
        # Task 5 adds the error-page wrapper; until then the rejection
        # propagates as an AutomationError. Being rejected IS the pass
        # condition here -- the assertions below hold either way.
        pass
    from bin import data_store

    entry = data_store.get_webhook_by_name("poc-hook")
    if entry is not None:
        # If a script was deployed at all, nothing in it may be an
        # expression in the value position.
        with open(entry["script"], "r", encoding="utf-8") as handle:
            nodes = _assign_nodes(handle.read())
        for name in ("server_url", "client_id"):
            assert isinstance(nodes[name], ast.Constant), (
                f"{name} is a {type(nodes[name]).__name__} in the "
                f"deployed script: the injection is still open"
            )
    # Either way the payload must never have run.
    assert not os.path.exists(marker), "the injected payload executed"


NON_FINITE_NUMERICS = ["inf", "-inf", "nan", "Infinity", "1e400", "-1e400"]


@pytest.mark.parametrize("value", NON_FINITE_NUMERICS)
def test_non_finite_numeric_is_rejected(value):
    """repr(float("inf")) is the bare word `inf`, which is not a
    builtin, so the numeric token (written bare) produced
    `COOLDOWN_HOURS = inf` -- NameError on the first trigger. The F821
    guard runs against the template, not the deployed copy, so only
    enable-time validation catches this.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "label": "Cooldown Hours",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
            workflow,
            {"COOLDOWN_HOURS": value},
            [],
            "",
        )


def test_huge_integer_is_rejected_rather_than_becoming_inf():
    """An integer string past CPython's ~4300-digit limit fails int(),
    then float()s to inf and shipped as the bare word `inf`.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "label": "Cooldown Hours",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
            workflow,
            {"COOLDOWN_HOURS": "9" * 5000},
            [],
            "",
        )


def test_unicode_digit_numeric_is_rejected():
    """int("٣") is 3 and int("１２") is 12, so a unicode digit silently
    became a different number than the glyphs an admin typed. Numerics
    are ASCII-only by deliberate choice.
    """
    from views import template_view
    from views._type_handlers.base import AutomationError

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "label": "Cooldown Hours",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    for value in ("٣", "１２"):
        with pytest.raises(AutomationError):
            template_view.substitute_params(
                "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
                workflow,
                {"COOLDOWN_HOURS": value},
                [],
                "",
            )


@pytest.mark.parametrize(
    "value,expected",
    [("24", 24), ("  7  ", 7), ("+5", 5), ("1e5", 100000.0), ("0.5", 0.5)],
)
def test_numeric_leniency_is_deliberate(value, expected):
    """Documented, intentional leniency: whitespace, a leading +, and
    exponent form are all things an admin plausibly types. Pinned so the
    behaviour is a decision rather than an accident.
    """
    from views import template_view

    workflow = {
        "config_params": [
            {
                "key": "COOLDOWN_HOURS",
                "token": "__JAWA_COOLDOWN_HOURS__",
                "type": "number",
            }
        ]
    }
    result = template_view.substitute_params(
        "COOLDOWN_HOURS = __JAWA_COOLDOWN_HOURS__\n",
        workflow,
        {"COOLDOWN_HOURS": value},
        [],
        "",
    )
    namespace = {}
    exec(compile(result, "generated.py", "exec"), namespace)
    assert namespace["COOLDOWN_HOURS"] == expected


# All ASCII, so isascii() passed, and none were in the structural
# blocklist. NUL makes the deployed .py fail to compile outright; the
# rest produce malformed XML or get silently rewritten by the parser.
RAW_CONTROL_CHARS = ["\x00", "\r", "\x0c", "\x0b", "\x1b", "\t", "\x7f"]


@pytest.mark.parametrize("char", RAW_CONTROL_CHARS)
def test_raw_param_rejects_control_characters(char):
    from views import template_view
    from views._type_handlers.base import AutomationError

    with pytest.raises(AutomationError):
        template_view.substitute_params(
            "<string>__JAWA_WIFI_SSID__</string>",
            _raw_workflow(),
            {"wifi_ssid": f"Corp{char}WiFi"},
            [],
            "",
        )


def test_raw_nul_byte_cannot_reach_a_deployed_script(
    logged_in_client, jawa_env, enable_form
):
    """A NUL in the SSID used to be accepted, and `compile()` then
    refused the deployed file ("source code string cannot contain null
    bytes") on the first trigger -- the script never ran.
    """
    form = enable_form(
        "return-to-service",
        webhook_name="nul-hook",
        wifi_ssid="Corp\x00WiFi",
    )
    try:
        logged_in_client.post("/templates/return-to-service/enable", data=form)
    except Exception:
        # Task 5 adds the error-page wrapper; until then the
        # AutomationError propagates. Nothing may be written either way.
        pass
    from bin import data_store

    assert data_store.get_webhook_by_name("nul-hook") is None
    assert not os.listdir(str(jawa_env.scripts_dir))
