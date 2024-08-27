# Jamf Automation and Webhook Assistant ("JAWA") Version 3.1.0

<p align="center"> <img src="https://github.com/jamf/JAWA/blob/master/static/img/jawa_icon.png" width="384"/> </p>


JAWA allows an IT Administrator to focus on providing the best end user experience through automation.

***[!]** NOTE: Always test automations in a dev/eval environment before deploying to production.*

## What is JAWA?

JAWA, the Jamf Automation and Webhook Assistant, is a web server designed to streamline automation workflows with Jamf Pro and other services. It features a webhook receiver for real-time automation and a crontab for scheduled script execution and report generation. JAWA simplifies the creation of time-saving workflows for Jamf Pro admins, providing a user-friendly framework to connect multiple services seamlessly within an organization.


*Check out [JAWA on the Jamf Marketplace](https://marketplace.jamf.com/details/jawa/) for screenshots.*

*Read the [JAWA Admin Guide](https://github.com/jamf/JAWA/wiki) too!*

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
      curl -O https://raw.githubusercontent.com/jamf/JAWA/master/bin/installer.sh && sudo bash ./installer.sh
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

## Releases

Find JAWA releases [here.](https://github.com/jamf/JAWA/releases)


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