# JAWA Test Suite

Smoke tests for the JAWA web console and webhook receiver. The suite
needs **no Jamf Pro server, no network access, and no root** — Jamf
API calls are faked at the `requests` layer, script execution is
stubbed at `subprocess.Popen`, and all data files are redirected into
a per-test temp directory (test runs leave no artifacts in the repo).

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Layout

- `conftest.py` — fixtures: temp data layout (`jawa_env`), faked
  Jamf Pro (`fake_jamf`), and an authenticated console session
  (`logged_in_client`).
- `test_smoke_routes.py` — every blueprint surface renders without
  a 500; legacy redirects; anonymous access is rejected.
- `test_receiver.py` — `/hooks/<name>` auth validation and script
  execution pipeline.
- `test_login.py` — console login/logout against the faked Jamf.

## xfail markers

Tests marked `xfail(strict=True)` document known bugs (referenced by
issue ID). When the bug is fixed, the test will XPASS and fail the
run — remove the marker as part of the fix.
