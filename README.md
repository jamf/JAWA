# Jamf Automation and Webhook Assistant ("JAWA")
The JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

*[!] NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is it?

The Jamf Automation and Webhook Assistant, "JAWA", is a web server for hosting automation tools that interact with Jamf Pro, such as a webhook reciever, cron/timed exectution of scripts, and automated report generation.  JAWA makes it easier to implement automated workflows in Jamf Pro by providing a shared library of common tasks and also lets you use Webhooks and APIs of other SaaS products to automate multi-step or repetitive functions.  Scripts and workflows can be shared across organizations and teams. JAWA can reduce configuration time by reading and/or setting the Jamf Pro configurations required to run your automations. 

## How it works?

The JAWA runs on a Linux server and can be accessed via a GUI. Once installed, the IT Admin is able to use the JAWA as a one-stop shop/single pane of glass to upload, edit or adjust any automations they choose. The IT Admin gathers scripts or workflows they wish to implement, and using the GUI, they upload the scripts, name the scripts, and click go. The backend of the JAWA will make sure that based on event (time, webhook, etc.) the script/workflow runs and the desired action occurs. For webhooks, the JAWA utilizes a modified version of a the robust and open-source https://github.com/adnanh/webhook/. The webapp itself is built utilizing Python-Flask.

## Recommended Server Requriements
1. Ubuntu 18.04 or RHEL
2. 2GB RAM
3. 20GB Storage
4. A Jamf Pro account with permisison to perform the desired functions. For example, to configure webhooks, the  account must have access to read the Jamf Pro activation code and write permissions on webhooks. Similarly, an API script needs to run as a user with the appropriate create/read/update/delete permissions. 
5. Firewall rules to allow Inbound and/or outbound communcations to/from Saas and devices. These will depend on the functions you run in JAWA. For example, when imlementing Jamf Pro webhooks, Jamf Pro must be able to initiate connections to JAWA. When implementing a Jamf Pro API script, JAWA will need to initiate connections to Jamf Pro. When hosting a webapp used by devices, those devices must be able to initiate connections to JAWA.  

## How do I use it?

*See the "JAWA Administrators Guide" found in the [release](https://github.com/jamf/JAWA/releases) for more detailed installation and configuration instructions.*

Installation Steps:
1. Install an Ubuntu/RHEL server
2. Copy the JAWA installer to the server
3. Extract installer folder with `tar -xzvf <jawaInstaller>.tar.gz`
4. Change directories to the extracted folder
5. Run the installer with `sudo ./install.run`
6. Navigate to your FQDN to verify connection and completion
7. Log in with your Jamf Pro credentials
8. Follow the wizard to begin setting up your first webhook or automation

Configuration Steps:
1. Log in with your Jamf Pro Admin credentials
2. Select "Create New Webhook or Automation"
3. Fill in the form and attach your script

*NOTE: When completing a new webhook configuration, Jamf Pro (or source of webhook) will automatically be configured*

When scripting for webhooks, verifiy JSON structure sent from source:
[Jamf Pro Webhook Event Info](https://developer.jamf.com/webhooks)
[Okta Webhook Event Info](https://developer.okta.com/docs/reference/api/event-types/?q=event-hook-eligible)

Find realeases [here.](https://github.com/jamf/JAWA/releases)
