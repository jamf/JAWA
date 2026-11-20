"""Change an enabled Brander's settings, or update its script, in place.

Enabling a template writes one script with its settings substituted in.
Re-enabling would mint a new service token and web clip, so the four
non-secret Brander settings are edited directly in the deployed script,
and "refresh" rebuilds the script from the current template while
keeping every substituted value (credentials included, never shown).
"""

import ast
import os
import re
import tempfile
from typing import Any, Dict, List

from bin import brander_store

# setting key -> variable name in the script
SETTINGS = {
    "template_path": "TEMPLATE_PATH",
    "max_kb": "MAX_KB",
    "allow_person_fields": "ALLOW_PERSON_FIELDS",
    "wallpaper_setting": "WALLPAPER_SETTING",
}
# Everything the enable form substituted, kept across a refresh.
KEPT = [
    "self.server_url",
    "self.client_id",
    "self.client_secret",
    "EA_ID",
    "WALLPAPER_SETTING",
    "ASSETS_DIR",
    "FONT_PATH",
    "TEMPLATE_PATH",
    "MAX_KB",
    "ALLOW_PERSON_FIELDS",
]
DEFAULTS = {
    "ALLOW_PERSON_FIELDS": 'ALLOW_PERSON_FIELDS = "no"  # "yes" to allow user.*'
}
MARKER = "def template_wallpaper("


class SettingsError(Exception):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _line(name: str) -> re.Pattern:
    return re.compile(
        r"^([ \t]*" + re.escape(name) + r" = )(.*?)(\s*#.*)?$", re.M
    )


def is_brander_script(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    return MARKER in text and _line("TEMPLATE_PATH").search(text) is not None


def read_settings(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    found = {}
    for key, name in SETTINGS.items():
        match = _line(name).search(text)
        if match:
            try:
                found[key] = ast.literal_eval(match.group(2).strip())
            except (ValueError, SyntaxError):
                found[key] = None
    return found


def _validated(updates: Dict[str, str]) -> Dict[str, str]:
    """Python source for each setting, or SettingsError with every problem."""
    problems, source = [], {}
    if "template_path" in updates:
        value = str(updates["template_path"]).strip()
        if not value or len(value) > 300 or any(c in value for c in "\r\n\0#"):
            problems.append(
                "The template must be legacy, a file name or store:<name> (one line, at most 300 characters)."
            )
        elif value.startswith("store:") and "=" in value:
            try:
                brander_store.store_set(value[len("store:") :])
            except brander_store.StoreError as err:
                problems += [f"Store set: {p}." for p in err.problems]
            else:
                source["template_path"] = repr(value)
        else:
            source["template_path"] = repr(value)
    if "max_kb" in updates:
        text = str(updates["max_kb"]).strip()
        if not text.isdigit() or not 50 <= int(text) <= 20000:
            problems.append(
                "The largest wallpaper size must be a whole number of KB from 50 to 20000."
            )
        else:
            source["max_kb"] = str(int(text))
    if "allow_person_fields" in updates:
        value = str(updates["allow_person_fields"]).strip().lower()
        if value not in ("yes", "no"):
            problems.append("Allow personal fields must be yes or no.")
        else:
            source["allow_person_fields"] = repr(value)
    if "wallpaper_setting" in updates:
        text = str(updates["wallpaper_setting"]).strip()
        if text not in ("1", "2", "3"):
            problems.append(
                "The wallpaper target must be 1, 2 or 3 (lock screen, home screen, both)."
            )
        else:
            source["wallpaper_setting"] = text
    if problems:
        raise SettingsError(problems)
    return source


def validate(updates: Dict[str, str]) -> None:
    """Raise SettingsError listing every bad value; write nothing."""
    _validated(updates)


def _write(path: str, text: str) -> None:
    """Replace the script atomically, keeping its owner-only mode."""
    mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".brander-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def write_settings(path: str, updates: Dict[str, str]) -> None:
    source = _validated(updates)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    for key, value in source.items():
        pattern = _line(SETTINGS[key])

        def replace(match, value=value):
            return match.group(1) + value + (match.group(3) or "")

        text, count = pattern.subn(replace, text, count=1)
        if count != 1:
            raise SettingsError(
                [
                    f"This script has no {SETTINGS[key]} setting; update the script first."
                ]
            )
    compile(text, path, "exec")
    _write(path, text)


def refresh_script(path: str, template_source: str) -> None:
    """Rebuild a deployed Brander from the current template, keeping its
    shebang and every substituted value; settings the old script did not
    have get their defaults."""
    if not is_brander_script(path):
        raise SettingsError(
            ["This automation's script is not a Brander script."]
        )
    with open(path, encoding="utf-8") as handle:
        old = handle.read()
    with open(template_source, encoding="utf-8") as handle:
        new = handle.read()
    for name in KEPT:
        pattern = re.compile(r"^[ \t]*" + re.escape(name) + r" = .*$", re.M)
        if not pattern.search(new):
            continue
        found = pattern.search(old)
        line = found.group(0) if found else DEFAULTS.get(name)
        if line is None:
            raise SettingsError(
                [
                    f"The old script has no {name}; re-enable this Brander instead."
                ]
            )
        new = pattern.sub(lambda _: line, new, count=1)
    new = old.splitlines(True)[0] + new.split("\n", 1)[1]
    if "__JAWA_" in new:
        raise SettingsError(
            [
                "The updated script still has unfilled settings; re-enable this Brander instead."
            ]
        )
    compile(new, path, "exec")
    _write(path, new)
