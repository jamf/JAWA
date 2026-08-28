# Jamf Automation and Webhook Assistant ("JAWA") Version 3.2

<p align="center"> <img src="https://github.com/jamf/JAWA/blob/main/static/img/jawa_icon.png" width="384"/> </p>


JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

> **Prefer a hosted option?** JAWA is self-hosted — you run and maintain the server yourself. If you'd rather not operate infrastructure, **[Jamf Routines](https://learn.jamf.com/r/en-US/jamf-routines-documentation/jamf_workflow_automation)** is a Jamf-hosted, Jamf-supported automation service. You can run both — see [JAWA vs. Jamf Routines](#jawa-vs-jamf-routines) below.

***[!]** NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is JAWA?

JAWA, the Jamf Automation and Webhook Assistant, is a web server designed to streamline automation workflows with Jamf Pro and other services. It features a webhook receiver for real-time automation and a crontab for scheduled script execution and report generation. JAWA simplifies the creation of time-saving workflows for Jamf Pro admins, providing a user-friendly framework to connect multiple services seamlessly within an organization.


*Check out [JAWA on the Jamf Marketplace](https://marketplace.jamf.com/details/jawa/) for screenshots.*

*Read the [JAWA Admin Guide](https://github.com/jamf/JAWA/wiki) too!*

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

## Server Requirements

### General Server Requirements:

- Ubuntu 22.04+ or RHEL / Rocky 9.x+
- Minimum: 8GB RAM (16GB recommended)
- Minimum: 128GB Storage (512GB recommended)
- Minimum: 2 CPU Core (4 Cores recommended)
- Python 3.9+ (with pip)

> The installer uses the distribution's default `python3` to build JAWA's virtual environment, so
> the OS version is what determines the Python version. Ubuntu 20.04 ships Python 3.8 and
> RHEL/Rocky 8 ships Python 3.6, neither of which satisfies JAWA's dependencies — use Ubuntu 22.04
> or later, or RHEL/Rocky 9 or later.

### Network Requirements:

- Inbound port 443 from JPS for
  webhooks ([IPs for Jamf Cloud](https://docs.jamf.com/technical-articles/Permitting_InboundOutbound_Traffic_with_Jamf_Cloud.html))
- Optional: Inbound port 443 from your LAN/IP (for web console access)
- Outbound port 443 to JPS and auxiliary services (
  Okta, WorkDay, etc.)
- A public DNS entry for the JAWA FQDN

### Certificate Requirements:

- Jamf Pro connects to JAWA over HTTPS to send webhooks.  JAWA must present a valid certificate for Jamf Pro to trust the connection. 
- A Publicly Trusted SSL Certificate and corresponding private key (for nginx)
   - Note: A _Publicly Trusted Full-chain Certificate_ is preferred
  for `jawa.crt`(i.e., root CA + intermediate + leaf cert bundle) 


### Jamf Pro Requirements:
- Jamf Pro Server 10.35.0+ 

## How to Use JAWA

Refer to the "JAWA Administrators Guide" in the [current release](https://github.com/jamf/JAWA/releases) for detailed installation and configuration instructions.

### Installation Steps:

1. Verify that you meet the server requirements.
2. Rename the certificate to `jawa.crt` and the private key to `jawa.key`.
3. Ensure you are in the same directory as your `jawa.crt` and `jawa.key`.
4. Download and run the JAWA installer:

      ```bash 
      curl -O https://raw.githubusercontent.com/jamf/JAWA/main/bin/installer.sh && sudo bash ./installer.sh
      ``` 

5. After the installation is complete, go to your FQDN (e.g., https://jawa.company.com) in your web browser to continue with the web-based setup.

### Configuration Steps:

1. Log in to JAWA with your Jamf Pro URL and Jamf Pro Administrator Credentials.
2. Click the “Setup link in the JAWA Dashboard or click Setup in the top navigation.
3. Fill out the Server Setup form:
    - [required] JAWA Server Address FQDN (e.g., https://jawa.company.com) - this address must be resolvable by the Jamf Pro Server to send webhooks.
    - [recommended] Lock your JAWA to a primary Jamf Pro Server.
    - [optional] Add an alternate Jamf Pro Server.
4. Click Setup.
5. Set up your first webhook or timed automation.


When scripting for webhooks, verify JSON structure sent from source:

1. [Jamf Pro Webhook Event Info](https://developer.jamf.com/developer-guide/docs/webhooks)
2. [Okta Webhook Event Info](https://developer.okta.com/docs/reference/api/event-types/?q=event-hook-eligible)

## Writing Automation Scripts

JAWA runs **your** scripts in response to Jamf Pro (or Okta/custom) webhooks and on a schedule. A script can be written in any language JAWA's host can execute; the examples here are Python. This section describes the contract JAWA uses to call your script.

### How JAWA calls a webhook script

When a webhook fires, JAWA executes your script and passes the **entire event payload as a single JSON string in the first command-line argument** (`sys.argv[1]`). It does not use stdin, environment variables, or a file. Your script's first job is to parse it:

```python
import json
import sys

event_data = json.loads(sys.argv[1])   # the whole webhook payload
```

A Jamf Pro webhook payload has two top-level keys:

- `event_data["webhook"]` — event metadata (`webhookEvent`, `eventTimestamp`, `id`)
- `event_data["event"]` — the event's own fields (for example `groupAddedDevicesIds`, `name`)

### Output and status (webhook automations)

- Anything your script prints (stdout and stderr) is captured line-by-line into the JAWA log under the automation's name. Use `print()` for progress and diagnostics.
- Exit `0` for success. A **non-zero exit code is recorded as a failure** in the log.

### Credentials

JAWA does not inject Jamf Pro or third-party credentials into your script. A script that calls the Jamf Pro API authenticates itself (for example, requesting its own OAuth token). Store secrets in your script's own configuration, not in JAWA.

### Scheduled (timed) automations

A timed automation runs your script on a schedule with **no webhook payload** — `sys.argv[1]` is not present. If one script serves both paths, guard for it:

```python
import json
import sys

event_data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
```

Timed automations run under the system's cron, so a script's output and exit status are handled by cron (for example, in the host's mail/syslog), not captured in the JAWA log.

### Complete example

This bundled script (`data/workflows/scripts/smart_group_slack.py`) posts to Slack when devices join a smart group:

```python
#!/usr/bin/env python3
"""Send Slack notification on smart group membership change.

Webhook event: SmartGroupComputerMembershipChange
"""

import json
import requests
import sys
from datetime import datetime

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"


def main():
    event_data = json.loads(sys.argv[1])
    event = event_data["event"]

    id_list = event.get("groupAddedDevicesIds", [])
    if not id_list:
        print("No devices entered the group.")
        sys.exit(12)

    group_name = event.get("name", "Unknown Group")

    slack_data = {
        "attachments": [
            {
                "title": f"Smart Group Update: {group_name}",
                "text": f"{len(id_list)} device(s) added to {group_name}",
                "footer": "JAWA Webhook Automation",
                "ts": datetime.timestamp(datetime.now()),
            }
        ]
    }

    resp = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps(slack_data),
        headers={"Content-Type": "application/json"},
    )
    print(f"Slack notification: {resp.status_code}")


if __name__ == "__main__":
    main()
```

### Common mistakes

- **The payload is `sys.argv[1]`, not stdin, not an environment variable, and not a file.**
- **It is a JSON *string*** — you must `json.loads()` it before use.
- **The event fields are nested** under `event_data["event"]`, not at the top level.
- **Don't assume JAWA provides a Jamf Pro token** — your script authenticates itself.
- **On the timed path there is no `sys.argv[1]`** — guard for it if a script serves both.

## Releases

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)

### JAWA v3.2.0 release

**Upgrade notes — please read before upgrading**

- **v3.2 is the last release that can migrate a JAWA v2 install.** The v2 upgrade path works in
  this release and is unchanged. If you are still on v2, move to v3.2 before upgrading further.
- **Template webhooks you previously enabled will begin firing.** A bug meant enabled and
  imported template webhooks silently never triggered. Template webhooks run **without
  authentication by default** — anyone who knows the hook name can trigger one. Review your
  enabled templates and add webhook authentication in the automation's edit screen if an
  endpoint should be protected. Authenticated-by-default templates are planned for a future
  release.
- **New webhook names are validated more strictly.** `#` and `%` are no longer accepted in a new
  webhook name, because Jamf Pro cannot call a URL containing them. Existing automations are
  unaffected.
- **Minimum platform is now Ubuntu 22.04 or RHEL/Rocky 9, and Python 3.9.** The installer builds
  JAWA's virtual environment from the distribution's default `python3`, and JAWA's dependencies no
  longer support Python 3.8. Ubuntu 20.04 (Python 3.8) and RHEL/Rocky 8 (Python 3.6) can no longer
  run JAWA — RHEL/Rocky 8 in fact stopped being able to when JAWA moved to Flask 3, which the
  stated requirements had not caught up with. Check `python3 --version` on the host before
  upgrading.
- **Content JAWA ships inside `data/` is not upgraded in place.** The installer preserves your
  `data/` directory across an upgrade, which protects your automations and settings, but it also
  means the bundled template scripts and the webhook event catalog stay at the version you first
  installed. A fresh install gets the current copies.

- New features
    - **Bundled templates now work as shipped.** Every bundled template runs when triggered; two
      were incomplete sketches that failed immediately. Enabling a template also creates the
      matching webhook in Jamf Pro for you and files the automation under Jamf Pro, so its
      trigger event is visible and editable. Templates can be protected with Basic
      authentication at enable time.
    - **Importing a template package can create its webhook in Jamf Pro too** — a new *Create
      webhook in Jamf Pro?* option, on by default. Clear it to install the script locally only.
      Because the package name becomes part of the URL Jamf Pro calls, a name with spaces or
      other URL-unsafe characters is refused on that path; fix the package file, or clear the box
      to install locally under any name.
    - **Webhook Reference page** documenting the Jamf Pro webhook events with sample payloads.
      One event, `DeviceRateLimited`, is listed with its sample payload still pending.
    - **Admin-configurable session timeout** in Setup: 15 minutes (default), 1 hour, 4 hours, or
      8 hours, with hardened session cookies. The 15-minute default remains the most secure; the
      longer options are convenient for workflow testing but leave an unattended signed-in
      console exposed for longer. Choose deliberately.
    - Smoke-test harness and CI (ruff + pytest) running on every push and pull request.
    - Documentation for writing automation scripts.
    - Script Preview and Download Script now show the real substitution tokens rather than
      generic placeholder text, so a downloaded script is self-documenting.
    - Resource Files listing gained Size and Type columns.
- Bugfixes
    - Template webhooks now fire (see upgrade notes).
    - Configuration values containing `&`, quotes, or angle brackets — Microsoft Teams and Power
      Automate URLs, and some secrets — are no longer corrupted when written into a generated
      script.
    - Enabling a template no longer stores authentication values that locked the webhook out.
    - Imported template packages are validated before installation: a `.jawa.json` whose script
      is truncated or has a syntax error is rejected with the offending line number, instead of
      installing a webhook that fails silently when it fires.
    - Fixed a crash on templates whose trigger event was a boolean.
    - The 401 response from an inbound webhook no longer echoes the requested hook name back.
    - Rejected path traversal in template package import, and guarded the legacy redirect routes
      against open redirects.
    - Resource Files page: Download and Delete are no longer adjacent, identical buttons, Delete
      routes through the shared confirmation screen, and hidden files no longer leak into the
      listing.
    - The success-page Back button no longer re-submits the action it just completed.
    - Corrected dashboard links and removed dead Extras links.
    - Uploads between 1 MB and 16 MB no longer fail with an opaque error; the server upload cap
      is now set explicitly.
    - Setup strips trailing slashes from Jamf Pro URLs, so generated webhook URLs no longer
      contain double slashes.
    - Script uploads with no `#!` shebang are rejected with a clear message instead of failing
      cryptically at trigger time.
    - The session-timeout warning now survives laptop sleep and backgrounded tabs.
    - Fixed resource file deletion, added 403/405/500 error pages, and hardened receiver edge
      cases including malformed form payloads.
    - The "Setup Required" error page links directly to Setup.
- Removed
    - The *Enrollment Pipeline* template, which shipped as an incomplete outline and needs a
      device-assignment CSV contract that will be designed properly in a future release.
- Repository maintenance
    - Removed dead code (legacy MongoEngine, stale stubs).
    - `data/cron.json` is no longer tracked in git, so a checkout can no longer overwrite real
      cron definitions with an empty seed file.

### JAWA v3.1.1 release
- Bugfix
 - Resolved #49
- Repository Maintenance

### JAWA v3.1.0 release
- New features
    - enhanced UI, mobile-friendly view
    - unified installer
    - enhanced script cleanup routine
- Bugfixes
    - improved error handling
    - sanitized user inputs to prevent XSS exploits 
    - unified installer that does not overwrite nginx defaults (resolving #31)
    - general bugfix and maintenance