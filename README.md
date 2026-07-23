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

- Ubuntu 20.04+ or RHEL 8.x+
- Minimum: 8GB RAM (16GB recommended)
- Minimum: 128GB Storage (512GB recommended)
- Minimum: 2 CPU Core (4 Cores recommended)
- Python 3.8+ (with pip)

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

### JAWA v3.2 release
- New features
    - smoke-test harness + CI (ruff + pytest) for safer releases
    - admin-configurable session timeout with hardened session cookies
    - documentation for writing automation scripts
- Bugfixes
    - template webhooks now fire correctly
    - rejected path traversal in template import
    - fixed resource deletion, error pages, and receiver edge cases
    - session-timeout warning now survives sleep/idle
    - "Setup Required" error page links directly to Setup
- Repository maintenance
    - removed dead code (legacy MongoEngine, stale stubs)

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