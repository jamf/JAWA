# JAWA
Jamf Automation and Webhook Assistant

The JAWA allows a an IT Administrator to focus on providing the best end user experience through automation!

*NOTE: Be advised that due to environmental differences, as always, it is best to test in your dev/eval server before deploying in production.*

## What is it?

The Jamf Automation and Webhook Assistant, JAWA, is a webapp that hosts various automation tools. Some of these tools include webhooks, cron/timed automations, and report generations.  Automations within Jamf Pro can now be accomplished, and IT Administrators can utilize Webhooks and APIs of other SaaS products to automate multi-step or repetitive tasks.  Thanks to the ease of use and modularity of the JAWA, scripts and workflows can be shared across organizations and teams.

## How it works?

The JAWA sits on a Linux server and can be accessed via a GUI. Once installed, the IT Admin is able to use the JAWA as a one-stop shop/single pane of glass to upload, edit or adjust any automations they choose. The IT Admin gathers scripts or workflows they wish to implement, and using the GUI, they upload the scripts, name the scripts, and click go. It's that easy. The backend of the JAWA will make sure that based on event (time, webhook, etc.) the script/workflow runs and the desired action occurs. For webhooks, the JAWA utilizes a modified version of a the robust and open-source https://github.com/adnanh/webhook/. The webapp itself is built utilizing Python-Flask.

*NOTE: JAWA and SaaS tools must have networking communication rules in place to properly execute desired automations. (i.e. Inbound from JAWA to Jamf Pro)*


## Minimum Server Requriements
1. Ubuntu 18.04 or RHEL
2. 4GB RAM
3. 50GB Storage
4. Inbound accessible from desired devices

*NOTE: Your Jamf Pro server must be able to be accessed with inbound from JAWA.*


## How do I use it?
FOR THE JAWA
1. Spin up a UBUNTU/RHEL server
2. Place installer folder in server
3. Unzip installer folder with `tar -xzvf <jawaInstaller>.tar.gz`
4. Change directories to the recently unzipped folder.
5. Run the installer with `sudo ./install.run`
6. Navigate to "https://jawa.server.com" to verify connection and completion
7. Log in with your Jamf Pro credentials
8. Follow the wizard to begin setting up your first webhook or automation