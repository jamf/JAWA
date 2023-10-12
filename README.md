# Jamf Automation and Webhook Assistant ("JAWA") Version 3.0.3

<p align="center"> <img src="https://github.com/jamf/JAWA/blob/master/static/img/jawa_icon.png" width="384"/> </p>


JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

***[!]** NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is it?

Jamf Automation and Webhook Assistant, "JAWA", is a web server for hosting automation tools that interacts with Jamf
Pro, Okta, and more. It includes a _webhook receiver_ for if-this-then-that automation workflows in real-time, and _crontab_
for the timed execution of scripts and automated report generation. JAWA is intended to make webhooks and automation
more accessible to admins of Jamf Pro by providing them with a simple framework with which they can design time-saving
workflows and to provide a conduit through which admins can connect multiple services within an organization.

*Check out [JAWA on the Jamf Marketplace](https://marketplace.jamf.com/details/jawa/) for screenshots.*

## How it works?

JAWA is a Python Flask web app which runs on Linux and can be accessed from a web-browser. Once installed, the IT Admin is
able to use JAWA to upload, edit, or adjust webhook and timed automations managed by JAWA. Automation scripts can be
uploaded by the IT admin and be configured to run when triggered (webhook), or run on a timer (cron). JAWA leverages
Jamf and Okta APIs when creating webhooks in their respective services.

## Server Requirements

General Server Requirements:

- Ubuntu 18.04+ or RHEL 7.x+
- Minimum: 512MB RAM (4GB recommended)
- Minimum: 12GB Storage (64GB recommended)
- Minimum: 1 CPU Core (2 Cores recommended)
- Python 3.7+ (with pip)

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

Jamf Pro Requirements
- Jamf Pro Server 10.35.0+ 

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
      curl -O https://raw.githubusercontent.com/jamf/JAWA/master/bin/ubuntu_installer.sh && sudo bash ./ubuntu_installer.sh
      ``` 
   2. RHEL installer:
       ```bash 
      curl -O https://raw.githubusercontent.com/jamf/JAWA/master/bin/rhel_installer.sh && sudo bash ./rhel_installer.sh
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

## Releases

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)


### JAWA v3.0.3 release
- New features
    - Jamf Pro API actions now use token-based authentication (resolving #32)
    - Option added for JAWA to return script results/output as part of a Custom webhook's response body (resolving #27)
    - Enhanced JAWA logging
    - Option added to use custom header authentication for Jamf Pro or Custom webhooks
