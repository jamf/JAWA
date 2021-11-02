# Jamf Automation and Webhook Assistant ("JAWA") Version 3.0.1

JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

***[!]** NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is it?

Jamf Automation and Webhook Assistant, "JAWA", is a web server for hosting automation tools that interacts with Jamf
Pro, Okta, and more. It includes a _webhook receiver_ for real-time if-this-then-that automation workflows and _crontab_
for the timed execution of scripts and automated report generation. JAWA is intended to make webhooks and automation
more accessible to admins of Jamf Pro by providing them with a simple framework with which they can design time-saving
workflows and further integrate with other services owned by their organization.

*Check out [JAWA on the Jamf Marketplace](https://marketplace.jamf.com/details/jawa/) for screenshots.*

## How it works?

JAWA is a Python Flask web app which runs on Linux and can be accessed via web-browser. Once installed, the IT Admin is
able to use JAWA to upload, edit, or adjust webhook and timed automations managed by JAWA. Automation scripts can be
uploaded by the IT admin and be configured to run when triggered (webhook), or run on a timer (cron). JAWA leverages
Jamf and Okta APIs when creating webhooks in their respective services.

## Server Requirements

General Server Requirements:

- Ubuntu 18.04+ or RHEL 7.x+
- Minimum: 512MB RAM (2GB recommended)
- Minimum: 5GB Storage (25GB recommended)
- Minimum: 1 CPU Core (2 Cores recommended)
- Python 3.6+ (with pip)

Network Requirements:

- Inbound port 443 from JPS for
  webhooks ([IPs for Jamf Cloud](https://docs.jamf.com/technical-articles/Permitting_InboundOutbound_Traffic_with_Jamf_Cloud.html))
- Inbound port 443 from LAN (for web access)
- Outbound port 443 to JPS and auxiliary services (
  Okta, WorkDay, etc.)

Certificate Requirements

- SSL/TLS certificate (publicly trusted) and private key
- A publicly trusted _full-chain certificate_ (bundle of root CA + intermediate + server cert) is preferred
  for `jawa.crt`

## How do I use it?

*See the "JAWA Administrators Guide" found in the [release](https://github.com/jamf/JAWA/releases) for more detailed
installation and configuration instructions.*

Installation Steps:

1. Complete server requirements
2. Rename certificate to jawa.crt and the private key to jawa.key
3. Ensure you are in the same directory as your jawa.crt and jawa.key
4. Download and run JAWA installer:
   1. Ubuntu installer: 

      ```bash 
      curl -O https://raw.githubusercontent.com/jamf/JAWA/develop/bin/ubuntu_installer.sh && sudo bash ./ubuntu_installer.sh
      ``` 
   2. RHEL installer:
       ```bash 
      curl -O https://raw.githubusercontent.com/jamf/JAWA/develop/bin/rhel_installer.sh && sudo bash ./rhel_installer.sh
      ``` 
5. After installation completes, navigate to your FQDN/IP (i.e., https://jawa.company.com) in your web browser to
   continue with the web-based setup

Configuration Steps:

1. Log in to JAWA with your Jamf Pro URL and Jamf Pro Administrator Credentials
2. Click the “Configure JAWA” link in the JAWA Dashboard or click Setup in the top-nav
3. Fill out the Server Setup form:
    1. [required] JAWA Server Address FQDN (i.e: https://jawa.company.com) - this address needs to be resolvable by the
       Jamf Pro Server to send webhooks
    2. [recommended] Lock your JAWA to a primary Jamf Pro Server
    3. [optional] Add an alternate Jamf Pro Server for
4. Click Setup
5. Set up your first webhook or timed automation

When scripting for webhooks, verify JSON structure sent from source:

1. [Jamf Pro Webhook Event Info](https://developer.jamf.com/developer-guide/docs/webhooks)
2. [Okta Webhook Event Info](https://developer.okta.com/docs/reference/api/event-types/?q=event-hook-eligible)

*NOTE: To ensure continuity, webhooks created via JAWA should be modified and deleted from JAWA as Jamf Pro (or source
of webhook) will automatically be configured/adjusted appropriately.*

## Version 3.0.1

- Views:
  - Success message clean-up
- Webhooks:
  - Additional display fields for `SmartGroupMobileDeviceMembershipChange` event


Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)

