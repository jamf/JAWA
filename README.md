# Jamf Automation and Webhook Assistant ("JAWA") Version 2.0
The JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

*[!] NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is it?

The Jamf Automation and Webhook Assistant, "JAWA", is a web server for hosting automation tools that interact with Jamf Pro, such as a webhook reciever, cron/timed exectution of scripts, and automated report generation.  JAWA makes it easier to implement automated workflows in Jamf Pro by providing a shared library of common tasks and also lets you use Webhooks and APIs of other SaaS products to automate multi-step or repetitive functions.  Scripts and workflows can be shared across organizations and teams. JAWA can reduce configuration time by reading and/or setting the Jamf Pro configurations required to run your automations. 

*Check out [screenshots.](https://github.com/jamf/JAWA/wiki/JAWA-Screenshots)*

## How it works?

The JAWA runs on a Linux server and can be accessed via a GUI. Once installed, the IT Admin is able to use the JAWA as a one-stop shop/single pane of glass to upload, edit or adjust any automations they choose. The IT Admin gathers scripts or workflows they wish to implement, and using the GUI, they upload the scripts, name the scripts, and click go. The backend of the JAWA will make sure that based on event (time, webhook, etc.) the script/workflow runs and the desired action occurs. For webhooks, the JAWA utilizes a modified version of a the robust and open-source https://github.com/adnanh/webhook/. The webapp itself is built utilizing Python-Flask.

## Recommended Server Requirements
General Server Requirements:
• Ubuntu 18.04 or RHEL 7.x
• 512MB RAM (2GB recommended)
• 5GB Storage (20GB recommended)
• 1 CPU Core (2 Cores recommended)
Network Requirements:
• Inbound port 443 from JPS (for webhooks) and LAN (for web access) • Outbound port 443 to JPS and auxiliary services (Okta, WorkDay, etc.) Certificate Requirements
• SSL/TLS certificate* and private key 

## How do I use it?

*See the "JAWA Administrators Guide" found in the [release](https://github.com/jamf/JAWA/releases) for more detailed installation and configuration instructions.*

Installation Steps:
1. Create server for JAWA with:
1. Port 443 open inbound/outbound.
2. Download JAWA installer (.run) from GitHub
3. Gather your SSL/TLS certificate and key
4. Rename certificate to jawa.crt and the private key to jawa.key
5. Transfer (scp) the JAWA installer and the SSL/TLS cert & key to the server.
6. Ensure you are in the same directory as your jawa.crt and jawa.key
7. Run the JAWA installer:
sudo ./install_jawa.run
8. Follow the prompts for installing The JAWA and choose your destiny (Clean Install, Upgrade, Uninstall, or Cancel)
9. After installation completes, navigate to your FQDN/IP (i.e., https://jawa.company.com) in your web browser to continue with the web-based setup.

Configuration Steps:
1. Log in to The JAWA with your Jamf Pro URL and Jamf Pro Administrator Credentials
2. Click the “Configure The JAWA” link in the Setup Options section
3. Type in the FQDN you gave The JAWA (i.e: https://jawa.company.com) - this address needs
to be resolvable by the Jamf Pro Server to send webhooks.
4. Click Utinni!

When scripting for webhooks, verifiy JSON structure sent from source:
1. [Jamf Pro Webhook Event Info](https://developer.jamf.com/webhooks)
2. [Okta Webhook Event Info](https://developer.okta.com/docs/reference/api/event-types/?q=event-hook-eligible)

*NOTE: To ensure continuity, webhooks created via JAWA should be modified and deleted from JAWA as Jamf Pro (or source of webhook) will automatically be configured/adjusted appropriately.*

## Version 2.0
- Second release!
- Python 3 build
- Moved Flask application to Waitress
- SSL Termination with NGINX
- JAWA and webhook moved to systemd
- Create and Delete Timed Automations
- Ability to lock authentication to specific Jamf Pro instance

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)

### Acknowledgments:
 Icon file ["Jawa star wars Icon"](https://icon-icons.com/icon/jawa-star-wars/76960) by [Sensible World](https://icon-icons.com/users/TTIQFLxRVkBQ8aKKlSTRZ/icon-sets/) is licensed under [CC BY-ND 4.0](https://creativecommons.org/licenses/by/4.0/).
