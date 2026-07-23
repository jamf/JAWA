"""Shared fixtures for the JAWA smoke-test harness.

JAWA resolves every data path as a module-level absolute constant
derived from the repo location, so these fixtures redirect each
module's constants into a per-test temp directory. Jamf Pro HTTP
calls are faked at the ``requests`` layer. No Jamf server, network
access, or root privileges are required to run the suite.
"""

import json
import logging
import os
import shutil
import sys

import pytest
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Importing bin.logger attaches a rotating file handler pointing at
# the repo's data/jawa.log. Swap it for a NullHandler so test runs
# leave no log artifacts in the working tree.
_LOG_PATH = os.path.join(REPO_ROOT, "data", "jawa.log")
_log_preexisting = os.path.exists(_LOG_PATH)

from bin import logger  # noqa: E402,F401

_root_logger = logging.getLogger("jawa")
for _handler in list(_root_logger.handlers):
    _handler.close()
    _root_logger.removeHandler(_handler)
_root_logger.addHandler(logging.NullHandler())

if not _log_preexisting and os.path.exists(_LOG_PATH):
    os.remove(_LOG_PATH)

import app as jawa_app  # noqa: E402
from bin import data_store  # noqa: E402
from views import (  # noqa: E402
    credential_view,
    home_view,
    log_view,
    resource_view,
    search_view,
    template_view,
)
from webhook import jawa_receiver  # noqa: E402

# The module-level Flask app is a singleton; register blueprints once.
jawa_app.register_blueprints()

JAMF_URL = "https://jamf.example.test"
TOKEN_EXPIRES = "2099-01-01T00:00:00.000+0000"


class FakeJamfResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload=None, status_code=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Fake Jamf error"
            )


def _fake_jamf_post(url, **kwargs):
    if url.endswith("/api/v1/auth/token"):
        return FakeJamfResponse(
            {"token": "test-token", "expires": TOKEN_EXPIRES}
        )
    if url.endswith("/api/v1/auth/invalidate-token"):
        return FakeJamfResponse({}, status_code=204)
    return FakeJamfResponse({})


def _fake_jamf_get(url, **kwargs):
    # /JSSResource/activationcode is the endpoint login uses to confirm
    # the host is really Jamf Pro; answer with the Jamf-shaped JSON so
    # _verify_jamf_access accepts it. Other GETs get a benign payload.
    if url.endswith("/JSSResource/activationcode"):
        return FakeJamfResponse(
            {"activation_code": {"organization_name": "Test Org"}}
        )
    return FakeJamfResponse({})


@pytest.fixture()
def fake_jamf(monkeypatch):
    """Fake every outbound HTTP verb JAWA uses against Jamf Pro."""
    monkeypatch.setattr(requests, "post", _fake_jamf_post)
    monkeypatch.setattr(requests, "get", _fake_jamf_get)
    monkeypatch.setattr(
        requests, "put", lambda *a, **k: FakeJamfResponse({})
    )
    monkeypatch.setattr(
        requests, "delete", lambda *a, **k: FakeJamfResponse({})
    )


class JawaEnv:
    """Handles to the per-test temp data layout."""

    def __init__(self, root):
        self.root = root
        self.data_dir = root / "data"
        self.scripts_dir = root / "scripts"
        self.files_dir = root / "resources" / "files"
        self.webhooks_file = self.data_dir / "webhooks.json"
        self.cron_file = self.data_dir / "cron.json"
        self.server_file = self.data_dir / "server.json"
        self.credentials_file = self.data_dir / "credentials.json"
        self.log_file = self.data_dir / "jawa.log"

    def add_webhook(self, entry):
        data = json.loads(self.webhooks_file.read_text())
        data.append(entry)
        self.webhooks_file.write_text(json.dumps(data))


@pytest.fixture()
def jawa_env(tmp_path, monkeypatch):
    """Point every module-level path constant at a temp directory."""
    env = JawaEnv(tmp_path)
    env.data_dir.mkdir()
    env.scripts_dir.mkdir()
    env.files_dir.mkdir(parents=True)

    env.webhooks_file.write_text("[]")
    env.cron_file.write_text("[]")
    env.credentials_file.write_text("[]")
    env.server_file.write_text(
        json.dumps(
            {
                "jawa_address": "https://jawa.example.test",
                "jps_url": JAMF_URL,
                "alternate_jps": "",
            }
        )
    )
    env.log_file.touch()
    shutil.copy(
        os.path.join(REPO_ROOT, "data", "time.json"),
        env.data_dir / "time.json",
    )

    webhooks = str(env.webhooks_file)
    cron = str(env.cron_file)
    server = str(env.server_file)
    creds = str(env.credentials_file)
    scripts = str(env.scripts_dir)
    log_file = str(env.log_file)

    monkeypatch.setattr(data_store, "WEBHOOKS_FILE", webhooks)
    monkeypatch.setattr(data_store, "CRON_FILE", cron)
    monkeypatch.setattr(data_store, "SERVER_FILE", server)
    monkeypatch.setattr(
        data_store, "TIME_FILE", str(env.data_dir / "time.json")
    )
    monkeypatch.setattr(data_store, "SCRIPTS_DIR", scripts)

    monkeypatch.setattr(home_view, "log_file", log_file)
    monkeypatch.setattr(home_view, "server_file", server)
    monkeypatch.setattr(home_view, "webhooks_file", webhooks)
    monkeypatch.setattr(home_view, "cron_file", cron)
    monkeypatch.setattr(
        home_view, "resources_dir", str(env.root / "resources")
    )
    monkeypatch.setattr(home_view, "files_dir", str(env.files_dir))

    monkeypatch.setattr(log_view, "log_file", log_file)
    monkeypatch.setattr(log_view, "server_json_file", server)

    monkeypatch.setattr(credential_view, "CREDENTIALS_FILE", creds)

    monkeypatch.setattr(resource_view, "log_file", log_file)
    monkeypatch.setattr(resource_view, "server_file", server)
    monkeypatch.setattr(
        resource_view, "resources_dir", str(env.root / "resources")
    )
    monkeypatch.setattr(resource_view, "files_dir", str(env.files_dir))

    monkeypatch.setattr(search_view, "WEBHOOKS_FILE", webhooks)
    monkeypatch.setattr(search_view, "CRON_FILE", cron)

    monkeypatch.setattr(template_view, "SCRIPTS_DIR", scripts)
    monkeypatch.setattr(template_view, "WEBHOOKS_FILE", webhooks)
    monkeypatch.setattr(template_view, "CREDENTIALS_FILE", creds)

    monkeypatch.setattr(jawa_receiver, "server_json_file", server)
    monkeypatch.setattr(jawa_receiver, "jp_webhooks_file", webhooks)
    monkeypatch.setattr(jawa_receiver, "scripts_dir", scripts)

    # app.py keeps its own globals, set via environment_setup().
    jawa_app.environment_setup(str(env.root))

    jawa_app.app.config.update(TESTING=True)
    jawa_app.app.secret_key = "jawa-test-secret"
    return env


@pytest.fixture()
def client(jawa_env):
    return jawa_app.app.test_client()


@pytest.fixture()
def logged_in_client(client, fake_jamf):
    """A test client holding an authenticated console session."""
    resp = client.post(
        "/login",
        data={
            "url": JAMF_URL,
            "username": "pytest-admin",
            "password": "hunter2",
        },
    )
    assert resp.status_code == 302, "login should redirect on success"
    assert "/dashboard" in resp.headers["Location"]
    return client
