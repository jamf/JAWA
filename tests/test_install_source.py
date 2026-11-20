"""The documented install must fetch released code from jamf/JAWA."""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM = "https://github.com/jamf/JAWA"


def _read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_installer_clones_jamf_jawa_by_default():
    installer = _read("bin", "installer.sh")
    assert f'repoUrl="{UPSTREAM}.git"' in installer
    clone = re.search(r"^\s*git clone .*$", installer, re.MULTILINE).group(0)
    assert '"$repoUrl"' in clone
    assert "ball42" not in installer


def test_readme_install_command_uses_jamf_jawa_main():
    readme = _read("README.md")
    command = re.search(
        r"^\s*curl -O (\S+installer\.sh) && sudo bash \./installer\.sh(.*)$",
        readme,
        re.MULTILINE,
    )
    assert command, "README has no installer command"
    url, args = command.group(1), command.group(2)
    assert url == (
        "https://raw.githubusercontent.com/jamf/JAWA/main/bin/installer.sh"
    )
    # No arguments: the installer defaults to main from jamf/JAWA.
    assert args.split() == []
