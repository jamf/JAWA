# JAWA architecture

This document explains how JAWA is put together, for someone who wants to change it or debug it. For installation and day-to-day use, see the [README](../README.md).

## The short version

JAWA is one Flask application served by Waitress on `127.0.0.1:8000`. nginx terminates TLS in front of it. The app has no database: all state is JSON files under `data/`, user scripts under `scripts/`, and entries in the `jawa` user's crontab. Scripts are run as child processes.

```
 Jamf Pro / Okta / custom sender            Admin browser            Managed device
          |  POST /hooks/<name>                  |  console pages          | web clip tap
          v                                      v                         v
      +-------------------------- nginx (443, TLS, X-Real-IP) --------------------------+
                                           |
                                    Waitress :8000
                                           |
                                      Flask app (app.py)
          +-------------------+-----------+-----------+--------------------+
          | webhook/          | views/    | bin/      | templates/ static/ |
          | jawa_receiver     | *_view    | data_store| (Jinja, CSS, JS)   |
          | tap_receiver| _type_    | auth      |                    |
          |                   |  handlers | logger ...|                    |
          +---------+---------+-----+-----+-----+-----+--------------------+
                    |               |           |
                    v               v           v
            scripts/<name>.*   data/*.json   crontab (jawa user)
            (child process)    data/*.log          |
                                                   v
                                          bin/run_cron.py <name>
                                          (runs the timed script)
```

## Code layout

| Path | Role |
|---|---|
| `app.py` | Creates the Flask app, loads the secret key, registers blueprints, defines the setup, cleanup, health-check and legacy-redirect routes, and starts Waitress in `main()`. |
| `webhook/jawa_receiver.py` | `POST /hooks/<name>`: authenticates the request, runs the script, returns a JSON result. Also holds the shared script runner. |
| `webhook/tap_receiver.py` | Device-facing `/tap/<service>` endpoint for Tap Action automations (a confirmation page on GET, script run on POST). |
| `views/*_view.py` | Console pages, one Flask blueprint per area: automations, credentials, log, resources, templates, search, webhook reference, home and login, and the Brander template store. |
| `views/_type_handlers/` | One handler class per automation type (`jamf`, `okta`, `custom`, `cron`, `tap`), all built on `base.py`. They own create, edit, delete and test for their type. |
| `bin/data_store.py` | The only module that reads and writes the JSON data files. Writes are atomic (temp file then rename) and guarded by a lock. |
| `bin/auth.py`, `bin/tokens.py` | Console sign-in against Jamf Pro, session handling, Jamf token renewal. |
| `bin/failure_alert.py` | The chat failure alert shared by webhook and timed runs: reads the URL from `server.json`, builds the text, POSTs it, and keeps the timed-run rate limit in `data/cron_alerts.json` (a tolerant read; writes go through `data_store.atomic_write_json`). Never raises. |
| `bin/run_cron.py` | Wrapper that cron calls for each timed automation so the output reaches the JAWA log, failures are recorded, and a failure sends the chat alert. |
| `bin/brander_*.py`, `bin/vendor_wallrender.py`, `data/workflows/lib/wallrender/` | The Brander feature: validated, versioned template packages rendered with a vendored copy of the `wallrender` library. |
| `bin/installer.sh` | Ubuntu and RHEL installer and upgrader: packages, `jawa` service account, venv, nginx, fail2ban, firewall, systemd unit. |
| `data/` | Runtime state (see below) plus `webhook_schemas.json` and `time.json`, which ship with the code. |
| `tests/` | The pytest suite. See [tests/README.md](../tests/README.md). |

## Automation types

An automation is a named entry plus a script. The type decides how it is triggered.

| Type | Trigger | Stored in |
|---|---|---|
| Jamf Pro webhook | Jamf Pro POSTs to `/hooks/<name>`. JAWA can create the webhook in Jamf Pro through its API. | `data/webhooks.json` |
| Okta event hook | Okta POSTs to `/hooks/<name>`. The one-time verification challenge is answered by `bin/okta_verification.py`. | `data/webhooks.json` |
| Custom webhook | Any sender POSTs to `/hooks/<name>`. | `data/webhooks.json` |
| Timed (cron) | A crontab line owned by the `jawa` user. | `data/cron.json` and the crontab |
| Tap action | A person taps a web clip on a device; the device calls `/tap/<service>` with a token. | `data/webhooks.json` (tag `tap`) |

Webhook-style entries share `webhooks.json` and are told apart by a `tag` field.

## Request flow: webhook

1. Jamf Pro (or another sender) POSTs JSON to `/hooks/<name>` through nginx.
2. `webhook_handler` rejects anything but POST, answers Okta verification challenges, and parses the JSON body (falling back to a form `payload` field).
3. `validate_webhook` finds the entry in `webhooks.json` and checks it against the credentials in the request (none, Basic, or an `x-api-key` header). Disabled entries and Tap Action entries are refused on this route.
4. `run_script` starts the script as a child process in its own process group, writes the payload to it, and enforces a timeout (`JAWA_SCRIPT_TIMEOUT`).
5. The outcome is recorded in `data/runs.json` and the log. The response is `200` or `202` with the script output when it ran, and a non-2xx status with an error when it did not, so Jamf Pro's delivery status reflects reality.

## Request flow: Tap Action

A GET renders a confirmation page from the query string and runs nothing. Only the POST from that page spawns the script. The token is compared in constant time, and a per-device cooldown (`data/tap_cooldowns.json`) stops repeated taps from launching duplicate runs.

## Request flow: timed automation

Saving a timed automation writes a crontab line for the `jawa` user that calls `bin/run_cron.py <name>`. At the scheduled time cron runs that wrapper, which looks the entry up in `cron.json`, runs the script, logs the output under the automation's name, and exits with the script's own exit code. A non-zero exit, including "no such automation" and "could not start", sends the chat failure alert through `bin/failure_alert.py`, the module the webhook receiver also uses. Webhook runs send it from a background thread and rate-limit in memory; a cron run sends it synchronously (10-second timeout) and rate-limits through `data/cron_alerts.json`. At startup `migrate_cron_commands()` rewrites older crontab lines to use the wrapper.

## Data and state

All paths are relative to the install directory (`/usr/local/jawa` on a standard install).

| File | Contents |
|---|---|
| `data/server.json` | Jamf Pro URL, JAWA address, allowed admin accounts. Written by the installer and the Setup page. |
| `data/webhooks.json` | Webhook, Okta, custom and Tap Action automations. |
| `data/cron.json` | Timed automations. |
| `data/credentials.json` | Credentials that scripts can use. Kept at mode 0600. |
| `data/runs.json` | Recent run history per automation. |
| `data/tap_cooldowns.json` | Tap action cooldown timestamps. |
| `data/cron_alerts.json` | Time of the last chat failure alert per timed automation (the 15-minute rate limit). Safe to delete. |
| `data/.secret_key` | Session signing key, created on first start (mode 0600) unless `JAWA_SECRET_KEY` is set. |
| `data/jawa.log`, `data/jawa-auth.log` | Application log (rotated at 100 MB, ten backups) and the failed-login log that fail2ban reads. |
| `data/brander_templates/` | Versioned Brander template packages, per Jamf Pro tenant. |
| `scripts/` | The automation scripts themselves. |
| `resources/` | Files uploaded from the Files page for scripts to use. |

Only `bin/data_store.py` should touch these files directly, so atomic writes and permissions stay in one place.

## Authentication model

- Console users sign in with a Jamf Pro account. JAWA exchanges the credentials for a Jamf Pro bearer token and keeps only that token in the session cookie, never the password. The token is renewed on each request while it is valid.
- The optional "Allowed admin accounts" list narrows who may sign in. An empty list allows every account Jamf Pro accepts.
- Sessions last 15 minutes. Cookies are `Secure` unless `JAWA_INSECURE_COOKIES=1`.
- Webhook endpoints are separate from the console: they use the per-automation credentials described above and never use the console session.
- Failed sign-ins are logged with the client address from `X-Real-IP`, which nginx sets, so fail2ban can ban repeat offenders.

## Design decisions

- **JSON files instead of a database.** The data is small, edited by one admin at a time, and easy to back up and inspect. Atomic writes and a lock in `data_store.py` cover the concurrency that exists.
- **Scripts as child processes.** An automation is any executable script, so admins are not tied to one language. The cost is that the console can run code on the server, which is why sign-in is restricted and uploads are validated.
- **cron plus a wrapper for schedules.** The operating system already schedules reliably. The wrapper exists so timed runs log like webhook runs instead of sending mail nobody reads.
- **Non-2xx when a script did not run.** Senders such as Jamf Pro treat 2xx as delivered, so JAWA only answers 2xx when the script actually ran.
- **Loopback bind behind nginx.** TLS, request logging, and the real client address are nginx's job. `JAWA_BIND` overrides the bind address for setups without nginx.
- **Vendored wallrender.** Brander renders with a pinned copy checked into `data/workflows/lib/`, refreshed with `bin/vendor_wallrender.py`, with the version recorded in `wallrender.lock.json`.
