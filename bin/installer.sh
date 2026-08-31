#!/bin/bash

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2023 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Greetings, friends.  This installer is intended for Ubuntu installations of JAWA.  It will not work well for other
# operating systems.  Run with sudo, and may the force be with you.
#
#  usage: sudo bash /path/to/ubuntu_installer.sh
#
# What does this installer do?
# - installs python and a webapp
# - installs dependencies (see requirements.txt)
# - installs and configures nginx for hosting the webapp
# - creates a systemd unit file for running the JAWA service
# - creates a jawa service account on the server for running the webapp and managing cron
# - enables ufw (firewall) and opens ports 22 (SSH) and 443 (JAWA).  The installer will prompt you for approval.
#
# What does this installer NOT do?
# - use root's crontab
# - mv your certs (it uses cp instead)
# - make the Kessel Run in 12 parsecs
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

installPackagesUbuntu() {
  /usr/bin/clear
  echo -ne "[#####                  ](28%) Configuring and updating apt... "
  echo -ne "[#####                  ](28%) Configuring and updating apt..." >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-add-repository universe >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/apt-get update >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  echo -ne '[######                  ](30%) Installing build tools from apt... '
  echo '[######                  ](30%) Installing build tools from apt...' >>/var/log/jawaInstall.log 2>&1
    /usr/bin/apt-get install -y -q build-essential git unzip zip nload tree >>/var/log/jawaInstall.log 2>&1 & spinner $! ""

  /usr/bin/clear
  /bin/echo -ne '[#######                ](35%) Installing nginx from apt... '
  /bin/echo '[#######                ](35%) Installing nginx... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q nginx >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  echo -ne '[########                ](40%) Installing python3-pip, python3-dev, and python3-venv from apt... '
  echo '[########                ](40%) Installing python3-pip, python3-dev, and python3-venv from apt...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q python3-pip python3-dev python3-venv >>/var/log/jawaInstall.log 2>&1 & spinner $! ""

   # Stop the hackers
  /usr/bin/clear
  /bin/echo -ne '[#########               ](45%) Installing fail2ban from apt... '
  /bin/echo '[#########               ](45%) Installing fail2ban from apt... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt install fail2ban -y -q >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
# For the bash inclined
  /usr/bin/clear
  /bin/echo -ne '[##########              ](50%) Installing jq from apt... '
  /bin/echo '[##########              ](50%) Installing jq from apt... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q jq >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear


}

installPackagesRedHat() {
  /usr/bin/clear
  echo -ne '[######                  ](30%) Installing git from yum... '
  echo '[######                  ](30%) Installing git from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y git >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
/usr/bin/clear
  echo -ne '[######                  ](31%) Installing unzip from yum... '
  echo '[######                  ](31%) Installing unzip from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y unzip >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
/usr/bin/clear
  echo -ne '[######                  ](32%) Installing zip from yum... '
  echo '[######                  ](32%) Installing zip from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y zip >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
/usr/bin/clear
  echo -ne '[######                  ](33%) Installing tree from yum... '
  echo '[######                  ](33%) Installing tree from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y tree >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
/usr/bin/clear
  echo -ne '[######                  ](34%) Installing epel-release from dnf... '
  echo '[######                  ](34%) Installing epel-release from dnf...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/dnf install -y epel-release >>/var/log/jawaInstall.log 2>&1 & spinner $! ""

  /usr/bin/clear
  /bin/echo -ne '[#######                ](35%) Installing nginx from yum... '
  /bin/echo '[#######                ](35%) Installing nginx... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y nginx >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  echo -ne '[########                ](40%) Installing python from yum... '
  echo '[########                ](40%) Installing python from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y python3 >>/var/log/jawaInstall.log 2>&1 & spinner $! ""

 # Stop the hackers
  /usr/bin/clear
  /bin/echo -ne '[#########               ](45%) Installing fail2ban from yum... '
  /bin/echo '[#########               ](45%)) Installing fail2ban from yum... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/dnf install fail2ban -y >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
# For the bash inclined
  /usr/bin/clear
  /bin/echo -ne '[##########              ](50%) Installing jq from yum... '
  /bin/echo '[##########              ](50%) Installing jq from yum... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y jq >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
}

installPackages() {
   local os=$(detect_os)

    case $os in
        "rocky" | "redhat")
            installPackagesRedHat
            ;;
        "ubuntu")
           installPackagesUbuntu
            ;;
        *)
            echo "Unsupported operating system"
            exit 1
            ;;
    esac
}

configure_nginx() {
   local os=$(detect_os)
    echo "Configuring nginx for $os">>/var/log/jawaInstall.log 2>&1
    case $os in
        "rocky" | "redhat")
            configure_nginx_redhat
            ;;
        "ubuntu")
           configure_nginx_ubuntu
            ;;
        *)
            echo "Unsupported operating system"
            exit 1
            ;;
    esac
}

# Function to detect the operating system
detect_os() {
    if [ -f /etc/redhat-release ]; then
        release_info=$(cat /etc/redhat-release)
        if [[ $release_info == *"Rocky"* ]]; then
            echo "rocky"
        else
            echo "redhat"
        fi
    elif [ -f /etc/lsb-release ]; then
        echo "ubuntu"
    else
        echo "unsupported"
    fi
}


# Function to install Nginx based on the detected operating system
configure_firewall() {
    local os=$(detect_os)

    case $os in
        "rocky" | "redhat")
            # RedHat | Rocky Firewall
            /usr/bin/firewall-cmd --zone=public --add-port=443/tcp --permanent
            /usr/bin/firewall-cmd --zone=public --add-port=22/tcp --permanent
            ;;
        "ubuntu")
            # Ubuntu Firewall
            ufw allow 22 >>/var/log/jawaInstall.log 2>&1
            ufw allow 443 >>/var/log/jawaInstall.log 2>&1
            ufwStatus=$(ufw status | grep -i status)
            if [ "$ufwStatus" != "Status: active" ]; then
              /bin/echo ""
              /bin/echo ""
              /bin/echo ""
              /bin/echo "NOTE: the OS firewall is being enabled, and ports 22 (SSH) and 443 (JAWA) are being opened inbound.
              If you use another port for SSH you should enable ufw manually and allow your custom port before proceeding with the installation."
              ufw enable
            fi
            ;;
        *)
            echo "Unsupported operating system"
            exit 1
            ;;
    esac
}

readme() {

  /usr/bin/clear

  printf '\e[8;90;191t'
  /usr/bin/clear

  /bin/echo "A long time ago, in a GitHub repo far, far away...

       __       ___   ____    __    ____  ___ 
      |  |     /   \  \   \  /  \  /   / /   \  
      |  |    /  ^  \  \   \/    \/   / /  ^  \ 
.--.  |  |   /  /_\  \  \            / /  /_\  \  
|  \`--'  |  /  _____  \  \    /\    / /  _____  \  
 \______/  /__/     \__\  \__/  \__/ /__/     \__\  

                        v3.2.0


Welcome to the Jamf Automation and Webhook Assistant, we hope it provides the solution you are looking for.

Please make sure you:

*  have a full-chain server certificate and private key in $currentDir
*  Certificate must be named jawa.crt
*  Private key file must be named jawa.key
*  Note: if upgrading from v2, choose the upgrade path /usr/local
"
}

# Minimum Python minor version. Werkzeug's patched releases (3.1.4+) require
# Python >= 3.9, and there is no patched Werkzeug for 3.8 -- PyPI serves
# nothing above 3.0.6 to a 3.8 interpreter. So "runs on 3.8" and "ships
# without the open Werkzeug advisory" are mutually exclusive.
jawaMinPyMinor=9
werkzeugPy38Fallback="3.0.6"
holdWerkzeug="no"

# Colour, as raw ANSI rather than tput: a server's terminfo frequently does not
# know a modern $TERM forwarded over SSH (see the TERM fallback at the bottom),
# and every tput call then fails. printf puts real ESC bytes into these
# variables, so a plain `/bin/echo "${cRed}..."` prints them -- this script has
# never relied on `echo -e`, whose behaviour differs between shells and builds.
#
# All six are empty unless stdout is a terminal, so a redirected run stays
# clean, and the >>jawaInstall.log lines are written uncoloured on purpose: the
# log must stay greppable. NO_COLOR is honoured (https://no-color.org).
initColour() {
  cReset=""
  cBold=""
  cRed=""
  cGreen=""
  cYellow=""
  cDate=""
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    cReset=$(printf '\033[0m')
    cBold=$(printf '\033[1m')
    cRed=$(printf '\033[1;31m')
    cGreen=$(printf '\033[1;32m')
    cYellow=$(printf '\033[1;33m')
    cDate=$(printf '\033[36m')
  fi
}

# Pads a role label to a fixed width BEFORE it is wrapped in colour. Padding
# afterwards would count the ESC bytes toward the field width and misalign the
# column by exactly the length of the escape sequence.
certLabel() {
  printf "%-${2:-8}s" "$1"
}

normalizeInstallDir() {
  # Strip trailing slashes so "$installDir/jawa" cannot become
  # "/usr/local//jawa". The paths were inconsistent -- one assignment used
  # "/usr/local/" while two others used "/usr/local" -- which put a double
  # slash into the systemd unit's ExecStart, the pip -r argument, and the
  # final "JAWA installed at" line. Harmless to the kernel, but it makes
  # the unit file and the logs look broken and defeats string comparison
  # of paths. Keep "/" itself intact rather than reducing it to "".
  while [ "$installDir" != "/" ] && [ "${installDir%/}" != "$installDir" ]; do
    installDir="${installDir%/}"
  done
}

checkPythonFloor() {
  # Runs FIRST, before anything destructive. This used to be discovered at
  # the 85% mark -- after cleaninstall had already removed the operator's
  # working install -- so a 3.8 host was left with a dead service behind a
  # "[########################](100%) Installation complete!" message.
  if [ ! -x /usr/bin/python3 ]; then
    /bin/echo "Python 3 is not present at /usr/bin/python3."
    /bin/echo "JAWA requires Python 3.${jawaMinPyMinor} or later. Install it and run this installer again."
    /bin/echo "Your existing JAWA install, if any, has NOT been modified. Exiting..."
    exit 2
  fi
  local pyMajor pyMinor pyVer
  pyVer=$(/usr/bin/python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
  pyMajor=${pyVer%%.*}
  pyMinor=${pyVer##*.}
  if [ -z "$pyMajor" ] || [ -z "$pyMinor" ]; then
    /bin/echo "Could not determine the Python version reported by /usr/bin/python3."
    /bin/echo "Your existing JAWA install, if any, has NOT been modified. Exiting..."
    exit 2
  fi
  /bin/echo "Detected Python $pyVer" >>/var/log/jawaInstall.log 2>&1
  if [ "$pyMajor" -gt 3 ]; then
    return 0
  fi
  if [ "$pyMajor" -eq 3 ] && [ "$pyMinor" -ge "$jawaMinPyMinor" ]; then
    return 0
  fi
  if [ "${JAWA_ALLOW_UNPATCHED_WERKZEUG:-0}" = "1" ]; then
    holdWerkzeug="yes"
    /bin/echo ""
    /bin/echo "WARNING: Python $pyVer is below JAWA's 3.${jawaMinPyMinor} floor, and"
    /bin/echo "JAWA_ALLOW_UNPATCHED_WERKZEUG=1 is set. Werkzeug will be held at"
    /bin/echo "$werkzeugPy38Fallback, which is the newest release available to Python $pyVer and"
    /bin/echo "carries an OPEN, UNPATCHED security advisory. You are accepting that."
    /bin/echo "The supported fix is Ubuntu 22.04+ / RHEL-Rocky 9+ (Python 3.${jawaMinPyMinor}+)."
    /bin/echo ""
    /bin/echo "Holding Werkzeug at $werkzeugPy38Fallback for Python $pyVer per JAWA_ALLOW_UNPATCHED_WERKZEUG=1" >>/var/log/jawaInstall.log 2>&1
    /bin/sleep 5
    return 0
  fi
  /bin/echo ""
  /bin/echo "JAWA 3.2 requires Python 3.${jawaMinPyMinor} or later. This host has Python $pyVer."
  /bin/echo ""
  /bin/echo "  Ubuntu 20.04 ships Python 3.8 and RHEL/Rocky 8 ships 3.6; neither is supported."
  /bin/echo "  Supported: Ubuntu 22.04+ or RHEL/Rocky 9+."
  /bin/echo ""
  /bin/echo "  Reason: JAWA's Werkzeug security fix is only published for Python 3.${jawaMinPyMinor}+."
  /bin/echo "  There is no patched Werkzeug for Python $pyVer."
  /bin/echo ""
  /bin/echo "  To install anyway with an UNPATCHED Werkzeug ($werkzeugPy38Fallback), re-run with"
  /bin/echo "  JAWA_ALLOW_UNPATCHED_WERKZEUG=1 set, e.g.:"
  /bin/echo "      sudo JAWA_ALLOW_UNPATCHED_WERKZEUG=1 bash ./installer.sh"
  /bin/echo ""
  /bin/echo "Your existing JAWA install, if any, has NOT been modified. Exiting..."
  /bin/echo "Refusing to install: Python $pyVer is below the 3.${jawaMinPyMinor} floor." >>/var/log/jawaInstall.log 2>&1
  exit 2
}

# Prints a certificate's expiry date, or "unreadable" if it will not parse.
certExpiry() {
  local enddate
  enddate=$(/usr/bin/openssl x509 -enddate -noout -in "$1" 2>/dev/null) || {
    /bin/echo "unreadable"
    return
  }
  /bin/echo "${enddate#notAfter=}"
}

# 0 when the certificate is already expired. An unparseable file returns 1: a
# file we cannot read is not a file we can call expired.
certIsExpired() {
  /usr/bin/openssl x509 -noout -in "$1" >/dev/null 2>&1 || return 1
  ! /usr/bin/openssl x509 -checkend 0 -noout -in "$1" >/dev/null 2>&1
}

# 0 when the certificate both parses and has not expired -- i.e. nginx can
# actually serve it. `-checkend 0` already fails on an unreadable file, which
# is the behaviour we want here: garbage is not usable either.
certIsUsable() {
  /usr/bin/openssl x509 -checkend 0 -noout -in "$1" >/dev/null 2>&1
}

# Say so when the certificate JAWA will actually serve is expired or close to
# it. An expired cert makes the console unreachable in a browser while every
# service check still passes, so silence here reads as an installer bug.
warnIfCertStale() {
  if certIsExpired "$1"; then
    /bin/echo ""
    /bin/echo "${cRed}WARNING${cReset}  the certificate JAWA will serve is ${cRed}EXPIRED${cReset}."
    /bin/echo "         $1"
    /bin/echo "         expired ${cDate}$(certExpiry "$1")${cReset}"
    /bin/echo "         Browsers will refuse the JAWA console until it is replaced."
    /bin/echo ""
    /bin/echo "WARNING: serving expired cert $1" >>/var/log/jawaInstall.log 2>&1
  elif /usr/bin/openssl x509 -noout -in "$1" >/dev/null 2>&1 &&
    ! /usr/bin/openssl x509 -checkend 2592000 -noout -in "$1" >/dev/null 2>&1; then
    /bin/echo ""
    /bin/echo "${cYellow}NOTE${cReset}     the certificate JAWA will serve expires within 30 days."
    /bin/echo "         $1"
    /bin/echo "         expires ${cDate}$(certExpiry "$1")${cReset}"
    /bin/echo ""
    /bin/echo "NOTE: cert $1 expires within 30 days" >>/var/log/jawaInstall.log 2>&1
  fi
}

install() {
  checkPythonFloor
  /usr/bin/clear
  # Variables


  # Certificates. nginx reads /etc/ssl/certs/jawa.{crt,key}, so a host that
  # already runs JAWA has a working pair there and the copy sitting in the
  # current directory is often a stale leftover from the first install. This
  # used to `cp` over the installed pair unconditionally, which is how a valid
  # certificate gets replaced by an expired one -- a downgrade the operator
  # only discovers later, as a browser error on a console the installer just
  # reported as a success. Never trade a valid certificate for an expired one,
  # and never make an upgrade re-supply certificates it already has.
  certsDir="/etc/ssl/certs"
  haveLocalCerts="no"
  haveInstalledCerts="no"
  if [ -f ./jawa.crt ] && [ -e ./jawa.key ]; then
    haveLocalCerts="yes"
  else
    if [ ! -f ./jawa.crt ]; then
      /bin/echo "Unable to locate jawa.crt in $currentDir" >>/var/log/jawaInstall.log 2>&1
    fi
    if [ ! -e ./jawa.key ]; then
      /bin/echo "Unable to locate jawa.key in $currentDir" >>/var/log/jawaInstall.log 2>&1
    fi
  fi
  if [ -f "$certsDir/jawa.crt" ] && [ -e "$certsDir/jawa.key" ]; then
    haveInstalledCerts="yes"
  fi

  if [ "$haveLocalCerts" == "no" ] && [ "$haveInstalledCerts" == "yes" ]; then
    # Upgrading a host that already has certificates. Demanding them in the
    # current directory again would push a working install into the
    # self-signed menu for no reason.
    /bin/echo ""
    /bin/echo "${cBold}Certificate: no jawa.crt/jawa.key here, so the installed one is kept.${cReset}"
    /bin/echo ""
    /bin/echo "  ${cBold}$(certLabel "IN USE")${cReset}  $certsDir/jawa.crt"
    /bin/echo "            ${cGreen}$(certLabel "VALID" 10)${cReset}  expires ${cDate}$(certExpiry "$certsDir/jawa.crt")${cReset}"
    /bin/echo ""
    /bin/echo "Keeping installed cert $certsDir/jawa.crt" >>/var/log/jawaInstall.log 2>&1
    warnIfCertStale "$certsDir/jawa.crt"
  elif [ "$haveLocalCerts" == "no" ]; then
    /bin/echo "Security requirements are not satisfied.
        Missing items are identified above--please provide the items in the installer directory before installing.

        Consult the admin guide for more information concerning certificates."
    certsMenu
  elif [ "$haveInstalledCerts" == "yes" ] && certIsUsable "$certsDir/jawa.crt" && ! certIsUsable ./jawa.crt; then
    # The copy in the current directory is expired or unreadable and the
    # installed one still works. Installing the bad copy would take the
    # console offline, so keep what works and say why.
    # Roles first, paths second. The operator reading this at a progress bar
    # needs to know which certificate is which and what it means before they
    # need to know where either one lives.
    if /usr/bin/openssl x509 -noout -in ./jawa.crt >/dev/null 2>&1; then
      certRejectState="EXPIRED"
      certRejectDetail="expired ${cDate}$(certExpiry ./jawa.crt)${cReset}"
      certRejectReason="has expired ($(certExpiry ./jawa.crt))"
    else
      certRejectState="UNREADABLE"
      certRejectDetail="not a valid certificate file"
      certRejectReason="is not a readable certificate"
    fi
    /bin/echo ""
    /bin/echo "${cBold}Certificate: keeping the one already in use. Nothing was replaced.${cReset}"
    /bin/echo ""
    /bin/echo "  ${cBold}$(certLabel "IN USE")${cReset}  $certsDir/jawa.crt"
    /bin/echo "            ${cGreen}$(certLabel "VALID" 10)${cReset}  expires ${cDate}$(certExpiry "$certsDir/jawa.crt")${cReset}"
    /bin/echo ""
    /bin/echo "  ${cBold}$(certLabel "OFFERED")${cReset}  $currentDir/jawa.crt"
    /bin/echo "            ${cRed}$(certLabel "$certRejectState" 10)${cReset}  $certRejectDetail"
    /bin/echo ""
    /bin/echo "  ${cBold}Impact:${cReset} none. JAWA keeps serving the certificate marked IN USE,"
    /bin/echo "  so the console stays reachable. The OFFERED file was left untouched."
    /bin/echo ""
    /bin/echo "  To install a new certificate, replace jawa.crt and jawa.key in"
    /bin/echo "  $currentDir and run this installer again."
    /bin/echo ""
    /bin/echo "Refused to overwrite valid $certsDir/jawa.crt with unusable ./jawa.crt (offered cert $certRejectReason)" >>/var/log/jawaInstall.log 2>&1
  else
    /bin/cp ./{jawa.crt,jawa.key} "$certsDir/"
    warnIfCertStale "$certsDir/jawa.crt"
  fi
  # checking for service
  if [ -e /etc/systemd/system/jawa.service ]; then
    status=$(/bin/systemctl is-active --quiet jawa && echo Service is running)
    echo "$status"
    if [ "$status" != "Service is running" ]; then
      projectDir=$(systemctl status jawa.service | grep -i /jawa/app.py | awk '{ print $3 }' | rev | cut -c 17- | rev | sed 's/ExecStart=//g')
    else
      projectDir=$(systemctl status jawa.service | grep -i /jawa/app.py | awk '{ print $3 }' | rev | cut -c 7- | rev)
    fi
    installDir=$(dirname "$projectDir")
    if [[ $installDir != "" ]]; then
      installDir="/usr/local"
    fi
    echo "JAWA directory detected at $installDir" >> /var/log/jawaInstall.log 2>&1
    read -r -p "Existing JAWA detected - would you like to upgrade? [y/n]:  " yn
    case $yn in
    [Yy]*)
      upgradeOption="yes"
      ;;
    [Nn]*) upgradeOption="no"
      ;;
    *) echo "Please answer yes or no." ;;
    esac
  fi
  if [ "$upgradeOption" != "yes" ]; then
    # prompting for install directory (upgrades reuse the detected installDir)
    read -r -p "Where would you like to install JAWA? [Press RETURN for $installDir]:  " new_dir
    while true; do
      if [ "$new_dir" != "" ]; then

        if [[ ${new_dir:0:1} == "/" ]]; then
          installDir="$new_dir"
        else
          installDir="/usr/local/$new_dir"
        fi
        # An operator answering "/opt/jawa/" must not produce "/opt/jawa//jawa".
        normalizeInstallDir
      fi
      read -p "The jawa project directory will be created in $installDir
         Please confirm [y|n]: " yn
      case $yn in
      [Yy]*)

        break
        ;;
      [Nn]*) read -r -p "Where would you like to install JAWA? [Press RETURN for $installDir]:  " new_dir ;;
      *) echo "Please answer yes or no." ;;
      esac
    done
  fi
  /usr/bin/clear
  echo -ne '[##                     ](10%) Reticulating splines... '
  echo '[##                     ](10%) Reticulating splines...' >>/var/log/jawaInstall.log 2>&1
  sleep 1 & spinner $! ""
  /usr/bin/clear
  echo -ne '[###                    ](15%) Creating jawa user... '
  echo -ne '[###                    ](15%) Creating jawa user... ' >>/var/log/jawaInstall.log 2>&1
  # Checking for jawa user
  if id "jawa" &>/dev/null; then
    echo 'jawa user exists' >>/var/log/jawaInstall.log 2>&1
  else
    echo 'Creating JAWA user...' >>/var/log/jawaInstall.log 2>&1
    su -c "useradd jawa -s /bin/bash" & spinner $! ""
    jawaPassword=$(
      tr -dc A-Za-z0-9 </dev/urandom | head -c 13
      echo ''
    )
    echo "jawa:$jawaPassword" | chpasswd
  fi
  /usr/bin/clear
  echo -ne '[####                   ](20%) Checking for previously installed JAWA project... '
  echo -ne '[####                   ](20%) Checking for previously installed JAWA project... ' >>/var/log/jawaInstall.log 2>&1
  # check for install dir's existence
  if [ -d "$installDir/jawa" ]; then
    #    echo -ne '[#####                  ](25%) Backing up previously installed JAWA project \r'
    /usr/bin/clear
    echo -ne '[#####                  ](25%) Backing up previously installed JAWA project... ' >>/var/log/jawaInstall.log 2>&1
    #    /bin/echo "JAWA project directory already exists at $installDir/jawa.  Backing up..."
    cleaninstall & spinner $! ""
  else
    /usr/bin/clear
    echo -ne "[#####                  ](25%) Creating JAWA project at $installDir/jawa... "
    echo -ne "[#####                  ](25%) Creating JAWA project at $installDir/jawa..." >>/var/log/jawaInstall.log 2>&1
    #    /bin/echo "Creating JAWA project directory at $installDir/jawa"
    sleep 1 & spinner $! ""
    /bin/mkdir -p "$installDir/jawa"
    /bin/chown -R jawa "$installDir/jawa"
  fi
  # Install Packages
  installPackages # 26-50%

  # Firewall
  /usr/bin/clear
  /bin/echo -ne '[###########             ](55%) Enabling firewall and opening ports 22 & 443... '
  /bin/echo '[###########             ](55%) Enabling firewall and opening ports 22 & 443 ' >>/var/log/jawaInstall.log 2>&1
  configure_firewall

  #Python check
  /usr/bin/clear
  /bin/echo -ne '[###########             ](56%) Safety check... '
  /bin/echo '[###########             ](56%) Safety check ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1  & spinner $! ""
  if [ -e /usr/bin/python3 ]; then
    /bin/echo "Python 3 installed." >>/var/log/jawaInstall.log 2>&1
  else
    /bin/echo "Python 3 not present, please install Python3 with pip prior to installation"
    /bin/echo "Exiting..."
    exit 2
  fi
  # `python3 -m pip` with no subcommand dumps 30 lines of usage onto the
  # operator's terminal, and its exit code is version-dependent -- newer
  # pip exits 1 for no-args, which made this abort with "python3-pip was
  # not installed successfully" while pip was in fact installed.
  /usr/bin/python3 -m pip --version >>/var/log/jawaInstall.log 2>&1
  if [ $? -eq 0 ]; then
    /bin/echo "python3-pip installed." >>/var/log/jawaInstall.log 2>&1
  else
    /bin/echo "python3-pip was not installed successfully via the installer.  Please install python3-pip manually and try again.  Exiting..." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "python3-pip was not installed successfully via the installer.  Please install python3-pip manually and try again."
    /bin/echo "Exiting..."
    exit 2
  fi

# change places!
  cd "$installDir"
  # getting available branches
#  branches=$(curl https://api.github.com/repos/jamf/jawa/branches | grep -i '"name":' | awk '{ print $2 }' | rev | cut -c 3- | rev | cut -c 2-)


  # cloning, like in that movie The Fly
  /usr/bin/clear
  /bin/echo -ne '[############            ](60%) Cloning the JAWA project from GitHub... '
  /bin/echo '[############            ](60%) Cloning the JAWA project from GitHub... ' >>/var/log/jawaInstall.log 2>&1

  git clone --branch "$branch" https://github.com/jamf/JAWA.git jawa >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  cloneStatus=$?
  # spinner propagates the background job's exit code; also confirm the clone actually landed
  if [ "$cloneStatus" -ne 0 ] || [ ! -d "$installDir/jawa/.git" ]; then
    /usr/bin/clear
    /bin/echo "Unable to clone the JAWA project (branch '$branch') from GitHub."
    /bin/echo "Check your network connection and that the branch exists, then see /var/log/jawaInstall.log for details."
    /bin/echo "Unable to clone the JAWA project (branch '$branch') from GitHub." >>/var/log/jawaInstall.log 2>&1
    exit 2
  fi
  # Restore backup?
  /usr/bin/clear
  /bin/echo -ne '[#############           ](64%) Checking for backups... '
  /bin/echo '[#############           ](64%) Checking for backups... ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1  & spinner $! ""
if [ -d "$currentDir/jawabackup-$timenow" ]; then
    backupJAWA="$currentDir/jawabackup-$timenow"
    while true; do
      /bin/echo ""
      if [ "$upgradeOption" == "yes" ]; then
        restoreBackup $currentDir $installDir
        break
      else
        read -p "Do you wish to restore your backup ($backupJAWA)  [y|n]: " yn
        case $yn in
        [Yy]*)
        restoreBackup $currentDir $installDir
        break
        ;;
      [Nn]*) break ;;
      *) echo "Please answer yes or no." ;;
        esac
      fi
    done
  fi
  # for gzip support in uwsgi
  #/usr/bin/apt-get install --no-install-recommends -y -q libpcre3-dev libz-dev

  /bin/echo -ne "[#############           ](65%) Setting permissions for $installDir/jawa... "
  /bin/echo "[#############           ](65%) Setting permissions for $installDir/jawa " >>/var/log/jawaInstall.log 2>&1
  chown -R jawa "$installDir/jawa" & spinner $! ""


   /usr/bin/clear
  # Create a venv for the app
  cd "$installDir/jawa"
  /usr/bin/clear
  /bin/echo -ne '[##############          ](70%) Creating venv... '
  /bin/echo '[##############          ](70%) Creating venv... ' >>/var/log/jawaInstall.log 2>&1
  python3 -m venv venv & spinner $! ""
  chown -R jawa "$installDir/jawa/venv"
  source "$installDir/jawa/venv/bin/activate"
  /usr/bin/clear
  /bin/echo -ne '[###############         ](75%) Upgrading pip and setuptools in venv... '
  /bin/echo '[###############         ](75%) Upgrading pip and setuptools in venv... ' >>/var/log/jawaInstall.log 2>&1
  "$installDir/jawa/venv/bin/python" -m pip install --upgrade pip setuptools >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  /bin/echo -ne '[################        ](80%) pip installing support modules (httpie and glances) in venv... '
  /bin/echo '[################        ](80%) pip installing support modules (httpie and glances) in venv... ' >>/var/log/jawaInstall.log 2>&1
  "$installDir/jawa/venv/bin/python" -m pip install --upgrade httpie glances >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  # flask requirements
  /usr/bin/clear
  /bin/echo -ne '[#################       ](85%) pip installing jawa requirements.txt file in venv... '
  /bin/echo '[#################       ](85%) pip installing jawa requirements.txt file in venv... ' >>/var/log/jawaInstall.log 2>&1
  if [ "$holdWerkzeug" = "yes" ]; then
    /bin/sed -i "s/^Werkzeug~=.*/Werkzeug~=$werkzeugPy38Fallback/" "$installDir/jawa/requirements.txt" >>/var/log/jawaInstall.log 2>&1
    /bin/echo "Held Werkzeug at $werkzeugPy38Fallback in requirements.txt" >>/var/log/jawaInstall.log 2>&1
  fi
  "$installDir/jawa/venv/bin/python" -m pip install -r "$installDir/jawa/requirements.txt" >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  # spinner propagates the background job's exit code (see the clone step).
  # Unchecked, a failed resolve here marched on to "100% Installation
  # complete!" and enabled a systemd unit that crash-looped on
  # ModuleNotFoundError -- the dependency failure was only visible in the log.
  requirementsStatus=$?
  if [ "$requirementsStatus" -ne 0 ] || ! "$installDir/jawa/venv/bin/python" -c 'import flask' >/dev/null 2>&1; then
    /usr/bin/clear
    /bin/echo ""
    /bin/echo "JAWA's Python dependencies failed to install, so the service cannot start."
    /bin/echo "This is NOT a missing python3/pip/git/curl -- those are present."
    /bin/echo ""
    /bin/echo "The failing lines are in /var/log/jawaInstall.log. To see them:"
    /bin/echo "    grep -E 'ERROR|No matching distribution' /var/log/jawaInstall.log | tail"
    /bin/echo ""
    /bin/echo "Aborting before the service is created." 
    /bin/echo "Python dependency install FAILED (status $requirementsStatus); flask not importable. Aborting." >>/var/log/jawaInstall.log 2>&1
    exit 2
  fi #
  #pip install --upgrade uwsgi
  /usr/bin/clear
  /bin/echo -ne '[##################      ](90%) Creating jawa service in systemd... '
  /bin/echo '[##################      ](90%) Creating jawa service in systemd... ' >>/var/log/jawaInstall.log 2>&1
  # Creating the JAWA webapp service
  if [ -e /etc/systemd/system/jawa.service ]; then
    /bin/systemctl stop jawa.service
    /bin/systemctl disable jawa.service
    rm -f /etc/systemd/system/jawa.service
  fi
  cat <<EOF >>/etc/systemd/system/jawa.service
[Unit]
Description=Jamf Automation & Webhooks Assistant
Documentation=https://github.com/jamf/JAWA
After=network.target

[Service]
User=jawa
WorkingDirectory=$installDir
ExecStart="$installDir/jawa/venv/bin/python3" $(pwd)/app.py
Restart=always


[Install]
WantedBy=multi-user.target
EOF
  sleep 1 & spinner $! ""
  /usr/bin/clear
  /bin/echo -ne '[###################     ](95%) Creating nginx configuration file... '
  /bin/echo '[###################     ](95%) Creating nginx configuration file ' >>/var/log/jawaInstall.log 2>&1
  configure_nginx
  /usr/bin/clear
  # Enabling and starting all services
  /bin/echo -ne '[####################    ](96%) Restarting services... \r'
  /bin/echo '[####################    ](96%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1
  #  /bin/echo "Starting JAWA systemd services..."
  /bin/systemctl daemon-reload >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[#####################   ](97%) Restarting services... \r'
  /bin/echo '[#####################   ](97%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl reset-failed >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[######################  ](98%) Restarting services... \r'
  /bin/echo '[######################  ](98%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl enable jawa.service >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart jawa.service >>/var/log/jawaInstall.log 2>&1
  jawaRestart=$?
  [ "$jawaRestart" -ne 0 ] && /bin/echo "systemctl restart jawa.service exited $jawaRestart" >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[####################### ](99%) Restarting services... \r'
  /bin/echo '[####################### ](99%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart nginx.service >>/var/log/jawaInstall.log 2>&1
  nginxRestart=$?
  [ "$nginxRestart" -ne 0 ] && /bin/echo "systemctl restart nginx.service exited $nginxRestart" >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[########################](100%) Installation complete! \r'
  /bin/echo '[########################](100%) Restarting services... untini! ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1.5

  /usr/bin/clear
  # Check every unit the install depends on and name the ones that failed.
  # Only jawa was ever verified, so a broken nginx reported "Installation
  # complete!" with an unreachable console -- and real installs failed nginx
  # repeatedly while this said nothing. The diagnostic differs per unit:
  # jawa's reason is in journalctl, nginx's is almost always a config or
  # certificate error, which `nginx -t` prints with the offending line.
  failedUnits=""
  for unit in jawa nginx; do
    if ! /bin/systemctl is-active --quiet "$unit"; then
      failedUnits="$failedUnits $unit"
    fi
  done
  if [ -n "$failedUnits" ]; then
      echo "Uh oh!  The installation finished, but these services are NOT running:$failedUnits"
      echo "Uh oh!  Services not running after install:$failedUnits" >>/var/log/jawaInstall.log 2>&1
      echo ""
      for unit in $failedUnits; do
        case "$unit" in
        jawa)
          echo "  jawa.service - the JAWA application itself."
          echo "    JAWA will not answer at all until this starts."
          echo "    See why:  journalctl -u jawa.service -n 50 --no-pager"
          ;;
        nginx)
          echo "  nginx.service - the TLS reverse proxy in front of JAWA."
          echo "    The web console is unreachable without it, even if jawa is healthy."
          echo "    Usually a config or certificate problem. Check the config first,"
          echo "    which names the offending file and line:"
          echo "      nginx -t"
          echo "    Then:  journalctl -u nginx.service -n 30 --no-pager"
          ;;
        esac
        echo ""
      done
      echo "The full installer log is at /var/log/jawaInstall.log"
      echo ""
      if [[ $jawaPassword != "" ]]; then
        /bin/echo "The following service account was created on your OS for running the JAWA application, and for creating the cron tasks."
        /bin/echo "It is not used for signing in to the web interface.  Please remember the password or change the credentials."
        /bin/echo "Username: jawa"
        /bin/echo "Password: $jawaPassword"
      fi
      exit 2
  else
      echo "jawa.service and nginx.service are both running." >>/var/log/jawaInstall.log 2>&1
  fi

  if [ -e "$installDir/jawa/static/jawadone.txt" ]; then
    /bin/cat "$installDir/jawa/static/jawadone.txt"
  fi

  /bin/echo "Installation complete...
  JAWA installed at $installDir/jawa"
  if [[ $jawaPassword != "" ]]; then
    /bin/echo "The following service account was created on your OS for running the JAWA application, and for creating the cron tasks."
    /bin/echo "It is not used for signing in to the web interface.  Please remember the password or change the credentials."
    /bin/echo "Username: jawa"
    /bin/echo "Password: $jawaPassword"
  fi
  # Enjoy your JAWA
  #  if [ -e /tmp/jawadone.txt ] && [ -d $installDir/ ]; then
  #    /bin/cat /tmp/jawadone.txt
  #    /bin/echo "DONE!  You can access JAWA from a web browser using the FQDN of this server."
  #  fi

  exit 0

}

uninstall() {
  # Removing the JAWA webapp service
  if [ -e /etc/systemd/system/jawa.service ]; then
    /bin/echo "Removing the JAWA service..." >>/var/log/jawaInstall.log 2>&1
    /bin/systemctl stop jawa.service >>/var/log/jawaInstall.log 2>&1
    /bin/systemctl disable jawa.service >>/var/log/jawaInstall.log 2>&1
    rm -f /etc/systemd/system/jawa.service >>/var/log/jawaInstall.log 2>&1
    /bin/echo "JAWA service removed." >>/var/log/jawaInstall.log 2>&1
  fi

  if [ -e /etc/nginx/sites-available/jawa ]; then
    /bin/echo "Removing the JAWA site from nginx..." >>/var/log/jawaInstall.log 2>&1
    rm -f /etc/nginx/sites-available/jawa >>/var/log/jawaInstall.log 2>&1
    rm -f /etc/nginx/sites-enabled/jawa >>/var/log/jawaInstall.log 2>&1
    /bin/systemctl restart nginx >>/var/log/jawaInstall.log 2>&1
    /bin/echo "JAWA site removed from nginx." >>/var/log/jawaInstall.log 2>&1
  fi
  /bin/echo "Resetting systemctl..." >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl reset-failed >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl daemon-reload >>/var/log/jawaInstall.log 2>&1

  /bin/echo "Checking for JAWA directory..." >>/var/log/jawaInstall.log 2>&1
  if [ -d "$installDir/jawa/" ]; then
    /bin/echo "Removing JAWA directory..." >>/var/log/jawaInstall.log 2>&1
    rm -rf "$installDir/jawa"
    /bin/echo "JAWA directory removed." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "These aren't the automatons you're looking for." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "You can go about your business." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "Move along." >>/var/log/jawaInstall.log 2>&1
    #    /bin/sleep 3
    /bin/echo "JAWA removed." >>/var/log/jawaInstall.log 2>&1
  fi

}
cleaninstall() {
  /usr/bin/clear
  echo -ne '[#####                  ](25%) Backing up previously installed JAWA project... '
  if [ -d "$installDir/jawa" ]; then
    /bin/mkdir -p $(pwd)/jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1
    if [ -d "$installDir/jawa/scripts" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the scripts $(pwd)/jawabackup-$timenow/... "
      /bin/echo "[#####                  ](25%) Backing up the scripts $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/scripts" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
    fi
    if [ -d "$installDir/jawa/resources" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the resources to $(pwd)/jawabackup-$timenow/... "
      /bin/echo "[#####                  ](25%) Backing up the resources to $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/resources" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
    fi
    if [ -d "$installDir/jawa/data" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the JAWA configuration files and logs to $(pwd)/jawabackup-$timenow/... "
      /bin/echo "[#####                  ](25%) Backing up the JAWA configuration files and logs to $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/data" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
    fi
    if [ -e "$installDir/jawa/static/img/jawa_icon.png" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the JAWA icon $(pwd)/jawabackup-$timenow/... "
      /bin/echo "[#####                  ](25%) Backing up the JAWA icon to $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp "$installDir/jawa/static/img/jawa_icon.png" ./jawabackup-$timenow/ >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
    fi

    uninstall
  fi

}

function shutdown() {
  tput cnorm # reset cursor
}
trap shutdown EXIT

function cursorBack() {
  echo -en "\033[$1D"
}

function spinner() {
  # make sure we use non-unicode character type locale
  # (that way it works for any locale as long as the font supports the characters)
  local LC_CTYPE=C

  local pid=$1 # Process Id of the previous running command

  case $(($RANDOM % 12)) in
  0)
    local spin='⠁⠂⠄⡀⢀⠠⠐⠈'
    local charwidth=3
    ;;
  1)
    local spin='-\|/'
    local charwidth=1
    ;;
  2)
    local spin="▁▂▃▄▅▆▇█▇▆▅▄▃▂▁"
    local charwidth=3
    ;;
  3)
    local spin="▉▊▋▌▍▎▏▎▍▌▋▊▉"
    local charwidth=3
    ;;
  4)
    local spin='←↖↑↗→↘↓↙'
    local charwidth=3
    ;;
  5)
    local spin='▖▘▝▗'
    local charwidth=3
    ;;
  6)
    local spin='┤┘┴└├┌┬┐'
    local charwidth=3
    ;;
  7)
    local spin='◢◣◤◥'
    local charwidth=3
    ;;
  8)
    local spin='◰◳◲◱'
    local charwidth=3
    ;;
  9)
    local spin='◴◷◶◵'
    local charwidth=3
    ;;
  10)
    local spin='◐◓◑◒'
    local charwidth=3
    ;;
  11)
    local spin='⣾⣽⣻⢿⡿⣟⣯⣷'
    local charwidth=3
    ;;
  esac

  local i=0
  tput civis # cursor invisible
  while kill -0 $pid 2>/dev/null; do
    local i=$(((i + $charwidth) % ${#spin}))
    printf "%s" "${spin:$i:$charwidth}"

    cursorBack 1
    sleep .1
  done
  tput cnorm
  wait $pid # capture exit code
  return $?
}

displayMenu() {
  while true; do
    read -r -p "Please select from the following options:

1. Install
2. Upgrade from V2
3. Cancel
 " opt
    case "$opt" in
    1)
      install
      ;;
    2)
      upgradeFromV2
      ;;
    3)
      exit
      ;;
    *)
      /bin/echo "Please choose an option:[ 1 | 2 | 3 ]:"
      continue
      ;;
    esac
  done
}
certsMenu() {
  while true; do
    read -r -p "Please choose your option:
        1.  Create Self-Signed certificate
        2.  Cancel and return with your own certificates
        " opt
    case "$opt" in
    1)
      selfsigned
      ;;
    2)
      exit
      ;;
    *)
      /bin/echo "Please choose an option [ 1 | 2 ]:"
      continue
      ;;
    esac
  done
}
selfsigned() {
  /bin/echo "Creating SSL cert" >>/var/log/jawaInstall.log 2>&1
  # Must land in $currentDir, not $installDir: install() re-checks ./jawa.crt
  # in the current directory, so writing elsewhere sent the operator back to
  # certsMenu forever unless they happened to be running from /usr/local.
  /usr/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 -subj "/C=US/ST=MN/L=Minneapolis/CN=jawa" -keyout "$currentDir/jawa.key" -out "$currentDir/jawa.crt" >>/var/log/jawaInstall.log 2>&1
  install
}
upgradeFromV2() {
  if [ ! -d "/usr/local/jawa/data" ]; then
    /bin/mkdir /usr/local/jawa/data
  fi
  /bin/echo "Disabling webhook.service..."
  /bin/sleep 1
  /bin/systemctl disable webhook.service
  /bin/systemctl stop webhook.service
  if [ ! -d "$currentDir/jawabackup-$timenow/v2" ]; then
    mkdir -p "$currentDir/jawabackup-$timenow/v2"
  fi
  if [ -e /usr/local/jawa/cron.json ]; then
    /bin/cp /usr/local/jawa/cron.json "$currentDir/jawabackup-$timenow/v2/"
  fi
  if [ -e /usr/local/jawa/jp_webhooks.json ]; then
    /bin/cp /usr/local/jawa/jp_webhooks.json "$currentDir/jawabackup-$timenow/v2/"
  fi
  if [ -e /usr/local/jawa/webapp/server.json ]; then
    /bin/cp /usr/local/jawa/webapp/server.json "$currentDir/jawabackup-$timenow/v2/"
  fi
  if [ -e /etc/webhook.conf ]; then
    /bin/cp /etc/webhook.conf "$currentDir/jawabackup-$timenow/v2/"
  fi
  /bin/echo "To complete the upgrade enter /usr/local when prompted for JAWA's installation directory..."
  installDir=/usr/local
  sleep 3
  install

}

restoreBackup() {
          local currentDir=$1
          local installDir=$2
          if [ -d "$currentDir/jawabackup-$timenow/v2/" ]; then
            if [ -e "$currentDir/jawabackup-$timenow/v2/cron.json" ]; then
              /bin/echo "Migrating cron..."
              /bin/cp "$currentDir/jawabackup-$timenow/v2/cron.json" "$currentDir/jawabackup-$timenow/data/"
            fi
            if [ -e "$currentDir/jawabackup-$timenow/v2/webhook.conf" ] || [ -e "$currentDir/jawabackup-$timenow/v2/jp_webhooks.json" ]; then
              /bin/echo "Migrating webhooks..."
              /usr/bin/python3 "$installDir/jawa/bin/v2_upgrade.py" "$currentDir/jawabackup-$timenow" >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
            fi
          fi
        # Guarded and logged, to match the backup half above. These four
        # copies previously ran bare: an upgrade from an install that
        # never had a scripts/ or resources/ directory -- the common
        # case, since neither is tracked -- printed "cp: ... No such
        # file or directory" straight onto the operator's terminal in
        # the middle of the progress bar.
        #
        # "$item/." rather than "$item/": the trailing-slash form means
        # different things to GNU and BSD cp (contents vs. the directory
        # itself), and "/." is the explicit contents-merge on both.
        for item in data resources scripts; do
          if [ -d "$currentDir/jawabackup-$timenow/$item" ]; then
            /bin/mkdir -p "$installDir/jawa/$item" >>/var/log/jawaInstall.log 2>&1
            /bin/cp -R "$currentDir/jawabackup-$timenow/$item/." "$installDir/jawa/$item/" >>/var/log/jawaInstall.log 2>&1
          fi
        done
        if [ -e "$currentDir/jawabackup-$timenow/jawa_icon.png" ]; then
          /bin/cp "$currentDir/jawabackup-$timenow/jawa_icon.png" "$installDir/jawa/static/img/jawa_icon.png" >>/var/log/jawaInstall.log 2>&1
        fi
}


# Function to install Nginx on Red Hat-based distributions
configure_nginx_redhat() {
  cat << EOF > /etc/nginx/conf.d/jawa.conf

upstream jawa {
    server 0.0.0.0:8000       weight=5;
}
server {
        #listen 80 default_server;
        #listen [::]:80 default_server;

        # SSL configuration
        #
         listen 443 ssl default_server;
         listen [::]:443 ssl default_server;
        #
        ssl_certificate /etc/ssl/certs/jawa.crt;
        ssl_certificate_key /etc/ssl/certs/jawa.key;

        server_name localhost;
        server_name_in_redirect off;
        client_max_body_size 16m;
        location / {
                # First attempt to serve request as file, then
                proxy_pass http://jawa;
                proxy_redirect     off;
                proxy_set_header   Host                 \$host;
                proxy_set_header   X-Real-IP            \$remote_addr;
                proxy_set_header   X-Forwarded-For      \$proxy_add_x_forwarded_for;
                proxy_set_header   X-Forwarded-Proto    \$scheme;
        }
 location /static {
       alias "$installDir/jawa/static";
   }
}
EOF
}


# Function to install Nginx on Ubuntu-based distributions
configure_nginx_ubuntu() {
    nginx_path="/etc/nginx/sites-available"
    nginx_enabled="/etc/nginx/sites-enabled"
    # Creating the nginx site
    if [ -e ${nginx_path}/jawa ]; then
      rm -f ${nginx_enabled}/jawa
      rm -f ${nginx_path}/jawa
    fi
    cat << EOF > ${nginx_path}/jawa
      server {
          #listen 80 default_server;
          #listen [::]:80 default_server;

          # SSL configuration
          #
           listen 443 ssl default_server;
           listen [::]:443 ssl default_server;
          #
          ssl_certificate /etc/ssl/certs/jawa.crt;
          ssl_certificate_key /etc/ssl/certs/jawa.key;

          server_name localhost;
          server_name_in_redirect off;
          client_max_body_size 16m;
          location / {
                  # First attempt to serve request as file, then
                  proxy_pass http://localhost:8000;
                  proxy_redirect     off;
                  proxy_set_header   Host                 \$host;
                  proxy_set_header   X-Real-IP            \$remote_addr;
                  proxy_set_header   X-Forwarded-For      \$proxy_add_x_forwarded_for;
                  proxy_set_header   X-Forwarded-Proto    \$scheme;
          }
      }

EOF

    # Enabling nginx
    /bin/ln -s ${nginx_path}/jawa ${nginx_enabled}

    if [ -e ${nginx_path}/default ]; then
      while true; do
        /bin/echo ""
        read -p "Do you wish to remove the default nginx configuration file (recommended) [y|n]: " yn
        case $yn in
        [Yy]*)
          rm -rf /etc/nginx/sites-available/default
          rm -rf /etc/nginx/sites-enabled/default
          break
          ;;
        [Nn]*) break ;;
        *) echo "Please answer yes or no." ;;
        esac
      done
    fi
}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
#                                            Application
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

/bin/echo "Initializing..."
# Environment Check
# Getting our bearings
currentDir=$(pwd)
installDir=/usr/local
timenow=$(date +%m-%d-%y_%T)
initColour

#branch="main"  # Default branch name if no arguments are provided

while [[ $# -gt 0 ]]; do
  key="$1"

  case $key in
    b|branch)
      branch="$2"
      shift 2  # Shift to the next argument
      ;;
    *)
      # Handle unknown options or arguments
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# If no branch argument was provided, default to "main" (production install path)
if [ -z "$branch" ]; then
  branch="main"
fi



# Checking for sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

# 47 `clear` calls and 3 `tput` calls assume the host's terminfo knows
# $TERM. A modern terminal forwarded over SSH (ghostty, kitty, wezterm) is
# often absent from a server's terminfo, and every one of them then fails --
# which also breaks the carriage-return progress redraw, so lines arrive
# mangled ("'xterm-ghostty': unknown terminal type.ing services...").
if ! tput clear >/dev/null 2>&1; then
  /bin/echo "TERM='${TERM:-}' is unknown to this host's terminfo; falling back to TERM=xterm." >>/var/log/jawaInstall.log 2>&1
  export TERM=xterm
fi

readme
displayMenu



