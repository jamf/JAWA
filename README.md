# Jamf Automation and Webhook Assistant ("JAWA") 4.0

<p align="center"> <img src="https://github.com/jamf/JAWA/blob/main/static/img/jawa_icon.png" width="384"/> </p>


JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

> **Prefer a hosted option?** JAWA is self-hosted — you run and maintain the server yourself. If you'd rather not operate infrastructure, **[Jamf Routines](https://learn.jamf.com/r/en-US/jamf-routines-documentation/jamf_workflow_automation)** is a Jamf-hosted, Jamf-supported automation service. You can run both — see [JAWA vs. Jamf Routines](#jawa-vs-jamf-routines) below.

***[!]** NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is JAWA?

JAWA, the Jamf Automation and Webhook Assistant, is a web server designed to streamline automation workflows with Jamf Pro and other services. It features a webhook receiver for real-time automation and a crontab for scheduled script execution and report generation. JAWA simplifies the creation of time-saving workflows for Jamf Pro admins, providing a user-friendly framework to connect multiple services seamlessly within an organization.


*Check out [JAWA on the Jamf Marketplace](https://marketplace.jamf.com/details/jawa/) for screenshots.*

*The guides live in the [JAWA wiki](https://github.com/jamf/JAWA/wiki).*

## JAWA vs. Jamf Routines

JAWA and [Jamf Routines](https://learn.jamf.com/r/en-US/jamf-routines-documentation/jamf_workflow_automation) both automate Jamf Pro workflows, in different ways.

| | **JAWA** | **Jamf Routines** |
|---|---|---|
| **Hosting** | Self-hosted (your server) | Jamf-hosted |
| **Maintenance** | You own the OS, TLS, updates, and uptime | Managed by Jamf |
| **Support** | Community / open source | Jamf-supported |
| **Automation model** | Your own scripts, triggered by webhooks or a schedule | Template-based workflows that connect tools to Jamf Pro |
| **Setup effort** | Provision a server, certificate, and DNS | Sign in and go |

**Choose JAWA** if you want full control, custom scripting, and don't mind running a server. **Choose Jamf Routines** if you'd rather not manage infrastructure and want a Jamf-supported, hosted experience. You can run both — they complement each other. For Jamf Routines availability and pricing, see the [Jamf Routines documentation](https://learn.jamf.com/r/en-US/jamf-routines-documentation/jamf_workflow_automation).

## Quick start

> **New in 4.0: the server requirements went up.** JAWA 4.0 needs Python 3.12+, which means
> Ubuntu 24.04+ or RHEL/Rocky 9.4+. Older hosts need an OS upgrade first; the installer checks
> and stops before it touches an existing install. See the
> [Release Notes](https://github.com/jamf/JAWA/wiki/Release-Notes) before upgrading.

| | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 24.04 or RHEL/Rocky 9.4 | |
| Python | 3.12 (the installer sets it up) | |
| RAM | 8 GB (for a trial, Ubuntu runs on 1 GB, RHEL needs 2 GB) | 16 GB |
| Storage | 128 GB | 512 GB |
| CPU | 2 cores | 4 cores |

You also need a DNS name Jamf Pro can reach, and a TLS certificate and key named `jawa.crt` and
`jawa.key` in the current directory. Then:

```bash
curl -O https://raw.githubusercontent.com/jamf/JAWA/main/bin/installer.sh && sudo bash ./installer.sh
```

Open your JAWA address in a browser and sign in with Jamf Pro administrator credentials.

## Documentation

- [Installation](https://github.com/jamf/JAWA/wiki/Installation): server, network, certificate and Jamf Pro requirements, setup
- [Writing Automation Scripts](https://github.com/jamf/JAWA/wiki/Writing-Automation-Scripts): how JAWA calls your script
- [Tap Actions](https://github.com/jamf/JAWA/wiki/Tap-Actions) and the [Brander guide](docs/BRANDER.md)
- [Operating a JAWA Server](https://github.com/jamf/JAWA/wiki/Operating-a-JAWA-Server): service, logs, backup, upgrade
- [Release Notes](https://github.com/jamf/JAWA/wiki/Release-Notes), including the 4.0 upgrade notes
- [Roadmap](https://github.com/jamf/JAWA/wiki/Roadmap)
- [Architecture](docs/ARCHITECTURE.md)

## Development

### Run JAWA locally

JAWA needs Python 3.9 or later. These commands create a virtual environment and start the app from a checkout. Everything it writes (logs, `data/server.json`, `data/.secret_key`) stays under `data/` in the checkout.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
JAWA_INSECURE_COOKIES=1 JAWA_ALLOW_UNPINNED_LOGIN=1 .venv/bin/python app.py
```

Browse to `http://127.0.0.1:8000`. Waitress serves plain HTTP, so without nginx in front you need `JAWA_INSECURE_COOKIES=1` for the session cookie to work, and `JAWA_ALLOW_UNPINNED_LOGIN=1` lets you sign in before a Jamf Pro URL is saved. Sign-in still goes to a real Jamf Pro server. Timed automations write to the running user's crontab, so use a throwaway account if you test them. `/healthz` returns `503` until `data/webhooks.json` and a `scripts/` directory exist; this is expected on a fresh checkout.

### Environment variables

| Variable | Effect |
|---|---|
| `JAWA_SECRET_KEY` | Session signing key. If unset, `data/.secret_key` is created and used. |
| `JAWA_BIND` | Address Waitress binds to. Default `127.0.0.1`. |
| `JAWA_INSECURE_COOKIES` | Set to `1` to allow session cookies over plain HTTP (local development only). |
| `JAWA_ALLOW_UNPINNED_LOGIN` | Set to `1` to allow sign-in before a Jamf Pro URL is saved (local development only). |
| `JAWA_SCRIPT_TIMEOUT` | Seconds a webhook script may run before it is stopped. |
| `JAWA_ALLOW_UNPATCHED_WERKZEUG` | Installer only: allow installation on Python 3.8 (see above). |

### Tests and lint

The suite needs no Jamf Pro server, network access, or root. See [tests/README.md](tests/README.md) for how the fixtures work.

```bash
.venv/bin/python -m pytest -q
```

```bash
.venv/bin/ruff check .
```

`ruff.toml` sets a 79-column line length. `ruff check` passes; `ruff format --check` currently reports unformatted files, so formatting is not enforced.

### How the code is organised

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) describes the components, data files, request flows, and the reasons behind the main design choices.

## Releases

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)
