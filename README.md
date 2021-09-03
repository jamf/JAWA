# Jamf Automation and Webhook Assistant ("JAWA") Version 3.0.0 (WIP)

JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

*[!] NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is it?

Jamf Automation and Webhook Assistant, "JAWA", is a web server for hosting automation tools that interact with Jamf
Pro, such as a webhook receiver, cron/timed execution of scripts, and automated report generation. JAWA makes it easier
to implement automated workflows in Jamf Pro by providing a shared library of common tasks and also lets you use
Webhooks and APIs of other SaaS products to automate multi-step or repetitive functions. Scripts and workflows can be
shared across organizations and teams. JAWA can reduce configuration time by reading and/or setting the Jamf Pro
configurations required to run your automations.

*Check out [screenshots.](https://github.com/jamf/JAWA/wiki/JAWA-Screenshots)*

## How it works?

The JAWA runs on a Linux server and can be accessed via a GUI. Once installed, the IT Admin is able to use the JAWA as a
one-stop shop/single pane of glass to upload, edit or adjust any automations they choose. The IT Admin gathers scripts
or workflows they wish to implement, and using the GUI, they upload the scripts, name the scripts, and click go. The
backend of the JAWA will make sure that based on event (time, webhook, etc.) the script/workflow runs and the desired
action occurs. The webapp is a Python Flask application.

## Server Requirements

General Server Requirements:

- Ubuntu 18.04+ or RHEL 7.x+
- Minimum: 512MB RAM (2GB recommended)
- Minimum: 5GB Storage (20GB recommended)
- Minimum: 1 CPU Core (2 Cores recommended)
- Python 3.6+

Network Requirements:

- Inbound port 443 from JPS for
  webhooks ([IPs for Jamf Cloud](https://docs.jamf.com/technical-articles/Permitting_InboundOutbound_Traffic_with_Jamf_Cloud.html))
- Inbound port 443 from LAN (for web access)
- Outbound port 443 to JPS and auxiliary services (
  Okta, WorkDay, etc.)

Certificate Requirements

- SSL/TLS certificate (publicly trusted) and private key

## How do I use it?

*See the "JAWA Administrators Guide" found in the [release](https://github.com/jamf/JAWA/releases) for more detailed
installation and configuration instructions.*

Installation Steps:

1. Complete server requirements
2. Download the installation script to the server
3. Rename certificate to jawa.crt and the private key to jawa.key
5. Ensure you are in the same directory as your jawa.crt and jawa.key
6. Run the JAWA installer:
   `sudo bash ./install_jawa.sh`
7. Follow the prompts for installing The JAWA and choose your destiny
8. After installation completes, navigate to your FQDN/IP (i.e., https://jawa.company.com) in your web browser to
   continue with the web-based setup.

Configuration Steps:

1. Log in to The JAWA with your Jamf Pro URL and Jamf Pro Administrator Credentials
2. Click the “Configure The JAWA” link in the Setup Options section
3. Type in the FQDN you gave The JAWA (i.e: https://jawa.company.com) - this address needs to be resolvable by the Jamf
   Pro Server to send webhooks.
4. Click Utinni!

When scripting for webhooks, verifiy JSON structure sent from source:

1. [Jamf Pro Webhook Event Info](https://developer.jamf.com/developer-guide/docs/webhooks)
2. [Okta Webhook Event Info](https://developer.okta.com/docs/reference/api/event-types/?q=event-hook-eligible)

*NOTE: To ensure continuity, webhooks created via JAWA should be modified and deleted from JAWA as Jamf Pro (or source
of webhook) will automatically be configured/adjusted appropriately.*

## Version 3.0.0 (WIP)

- Refactored:
  - Improved page views
  - New webhook engine
  - Relative paths
- Webapp:
    - New look and feel
    - Branding options
    - Log view
    - Files repo for script resources
- Webhooks:
    - Basic authentication for webhooks
    - Custom webhook
    - stdout/stderr logging
- JAWA and webhook moved to systemd
- Create and Delete Timed Automations
- Ability to lock authentication to specific Jamf Pro instance

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)

