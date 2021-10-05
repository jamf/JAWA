#!/bin/bash

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

/bin/echo "Initializing..."
# Environment Check
# Getting our bearings
currentDir=$(pwd)
installDir=$currentDir

# Checking for sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

timestamp() {
  /bin/echo ""
  /bin/echo -n $(date +"%D %T -")
  /bin/echo -n " "
}

readme() {

  /usr/bin/clear

  printf '\e[8;90;191t'
  /usr/bin/clear

  /bin/echo "Hi! Welcome to the JAWA, we hope these are the droids you are looking for.

Please make sure you:

*  have a full-chain server certificate and private key in $currentDir
*  Certificate must be named jawa.crt
*  Private key file must be named jawa.key
"
}

cancel() {
  /bin/echo "Canceling..."
  exit 0
}

install() {
  /usr/bin/clear
  # Variables
  nginx_path="/etc/nginx/sites-available"
  nginx_enabled="/etc/nginx/sites-enabled"

  x=0

  if [ ! -f ./jawa.crt ] >/dev/null 2>&1; then
    /bin/echo "Unable to locate jawa.crt in $currentDir" >>/var/log/jawaInstall.log 2>&1
    x=$(($x + 1))
  fi
  if [ ! -e ./jawa.key ] >/dev/null 2>&1; then
    /bin/echo "Unable to locate jawa.key in $currentDir" >>/var/log/jawaInstall.log 2>&1
    x=$(($x + 1))
  fi

  if [[ $x -ne 0 ]]; then
    /bin/echo "Security requirements are not satisfied.
        Missing items are identified above--please provide the items in the installer directory before installing.

        Consult the admin guide for more information concerning certificates."
    certsMenu
  fi
  /bin/cp ./{jawa.crt,jawa.key} /etc/ssl/certs/
  # prompting for install dir

  read -r -p "Where would you like to install JAWA? [Press RETURN for $installDir]:  " new_dir
  while true; do
    if [ "$new_dir" != "" ]; then

      if [[ ${new_dir:0:1} == "/" ]]; then
        installDir="$new_dir"
      else
        installDir="$currentDir/$new_dir"
      fi
    fi
    read -p "The jawa project directory will be created in $installDir
       Please confirm [y/n]: " yn
    case $yn in
    [Yy]*)

      break
      ;;
    [Nn]*) read -r -p "Where would you like to install JAWA? [Press RETURN for $installDir]:  " new_dir ;;
    *) echo "Please answer yes or no." ;;
    esac
  done

  /usr/bin/clear
  echo -ne '[##                     ](10%) Reticulating splines\r'
  echo '[##                     ](10%) Reticulating splines' >>/var/log/jawaInstall.log 2>&1

  echo -ne '[###                    ](15%) Creating jawa user \r'
  echo -ne '[###                    ](15%) Creating jawa user ' >>/var/log/jawaInstall.log 2>&1
  # Checking for jawa user
  if id "jawa" &>/dev/null; then
    echo 'jawa user exists' >>/var/log/jawaInstall.log 2>&1
  else
    echo 'Creating JAWA user...' >>/var/log/jawaInstall.log 2>&1
    su -c "useradd jawa -s /bin/bash"
    jawaPassword=$(
      tr -dc A-Za-z0-9 </dev/urandom | head -c 13
      echo ''
    )
    echo "jawa:$jawaPassword" | chpasswd
  fi
  echo -ne '[####                   ](20%) Checking for previously installed JAWA project \r'
  echo -ne '[####                   ](20%) Checking for previously installed JAWA project ' >>/var/log/jawaInstall.log 2>&1
  # check for install dir's existence
  if [ -d "$installDir/jawa" ]; then
    #    echo -ne '[#####                  ](25%) Backing up previously installed JAWA project \r'
    /usr/bin/clear
    echo -ne '[#####                  ](25%) Backing up previously installed JAWA project ' >>/var/log/jawaInstall.log 2>&1
    #    /bin/echo "JAWA project directory already exists at $installDir/jawa.  Backing up..."
    cleaninstall
  else
    /usr/bin/clear
    echo -ne "[#####                  ](25%) Creating JAWA project at $installDir/jawa \r"
    echo -ne "[#####                  ](25%) Creating JAWA project at $installDir/jawa \r" >>/var/log/jawaInstall.log 2>&1
    #    /bin/echo "Creating JAWA project directory at $installDir/jawa"
    /bin/mkdir -p "$installDir/jawa"
    /bin/chown -R jawa "$installDir/jawa"
  fi

  # Install some OS dependencies:
  /usr/bin/apt-add-repository universe >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  echo -ne '[######                  ](30%) Installing build tools from apt \r'
  echo '[######                  ](30%) Installing build tools from apt' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q build-essential git unzip zip nload tree >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  echo -ne '[#######                 ](35%) Installing python3-pip, python3-dev, and python3-venv from apt \r'
  echo '[#######                 ](35%) Installing python3-pip, python3-dev, and python3-venv from apt ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q python3-pip python3-dev python3-venv >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[########                ](40%) Installing nginx from apt \r'
  /bin/echo '[########                ](40%) Installing nginx ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q nginx >>/var/log/jawaInstall.log 2>&1
  # For the bash inclined
  /usr/bin/clear
  /bin/echo -ne '[#########               ](45%) Installing jq from apt \r'
  /bin/echo '[#########               ](45%) Installing jq from apt ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt-get install -y -q jq >>/var/log/jawaInstall.log 2>&1

  #Python check
  /usr/bin/clear
  /bin/echo -ne '[##########              ](50%) Safety check \r'
  /bin/echo '[##########              ](50%) Safety check ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1
  if [ -e /usr/bin/python3 ]; then
    /bin/echo "Python 3 installed." >>/var/log/jawaInstall.log 2>&1
  else
    /bin/echo "Python 3 not present, please install Python3 with pip prior to installation"
    /bin/echo "Exiting..."
    exit 2
  fi

  # for gzip support in uwsgi
  #/usr/bin/apt-get install --no-install-recommends -y -q libpcre3-dev libz-dev

  # Stop the hackers
  /bin/echo -ne '[###########             ](55%) Installing fail2ban from apt \r'
  /bin/echo '[###########             ](55%) Installing fail2ban from apt ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/apt install fail2ban -y -q >>/var/log/jawaInstall.log 2>&1

  # change places!
  cd "$installDir"
  # cloning, like in that movie The Fly
  /bin/echo -ne '[############            ](60%) Cloning the JAWA project from GitHub \r'
  /bin/echo '[############            ](60%) Cloning the JAWA project from GitHub ' >>/var/log/jawaInstall.log 2>&1
  git clone --branch develop https://github.com/jamf/JAWA.git jawa >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[#############           ](65%) Setting permissions for $installDir/jawa \r'
  /bin/echo '[#############           ](65%) Setting permissions for $installDir/jawa ' >>/var/log/jawaInstall.log 2>&1
  chown -R jawa "$installDir/jawa"

  /bin/echo -ne '[##############          ](70%) Enabling firewall and opening ports 22 & 443 \r'
  /bin/echo '[##############          ](70%) Enabling firewall and opening ports 22 & 443 ' >>/var/log/jawaInstall.log 2>&1
  ufw allow 22 >>/var/log/jawaInstall.log 2>&1
  ufw allow 443 >>/var/log/jawaInstall.log 2>&1
  /bin/echo ""
  /bin/echo ""
  /bin/echo ""
  /bin/echo "NOTE: the OS firewall is being enabled, and ports 22 (SSH) and 443 (JAWA) are being opened inbound.
  If you use another port for SSH you should enable ufw manually and allow your custom port before proceeding with the installation."
  ufw enable
  /usr/bin/clear
  # Create a venv for the app
  cd "$installDir/jawa"
  /bin/echo -ne '[###############         ](75%) Creating venv \r'
  /bin/echo '[###############         ](75%) Creating venv ' >>/var/log/jawaInstall.log 2>&1
  python3 -m venv venv
  chown -R jawa "$installDir/jawa/venv"
  source "$installDir/jawa/venv/bin/activate"
  /bin/echo -ne '[###############         ](75%) Upgrading pip and setuptools in venv \r'
  /bin/echo '[###############         ](75%) Upgrading pip and setuptools in venv ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install --upgrade pip setuptools >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[################        ](80%) pip installing support modules (httpie and glances) in venv \r'
  /bin/echo '[################        ](80%) pip installing support modules (httpie and glances) in venv ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install --upgrade httpie glances >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  # flask requirements
  /bin/echo -ne '[#################       ](85%) pip installing jawa requirements.txt file in venv \r'
  /bin/echo '[#################       ](85%) pip installing jawa requirements.txt file in venv ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install -r "$installDir/jawa/requirements.txt" >>/var/log/jawaInstall.log 2>&1 #
  #pip install --upgrade uwsgi
  /usr/bin/clear
  /bin/echo -ne '[##################      ](90%) Creating jawa service in systemd \r'
  /bin/echo '[##################      ](90%) Creating jawa service in systemd ' >>/var/log/jawaInstall.log 2>&1
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

  /bin/echo -ne '[###################     ](95%) Creating nginx configuration file \r'
  /bin/echo '[###################     ](95%) Creating nginx configuration file ' >>/var/log/jawaInstall.log 2>&1
  # Creating the nginx site
  if [ -e ${nginx_path}/jawa ]; then
    rm -f ${nginx_enabled}/jawa
    rm -f ${nginx_path}/jawa
  fi
  cat <<EOF >>${nginx_path}/jawa
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

  if [ -d ${nginx_path}/sites-available/default ]; then
    while true; do
      read -p "Do you wish to remove the default nginx configuration file (recommended) [y/n]: " yn
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
  /usr/bin/clear
  # Enabling and starting all services
  /bin/echo -ne '[####################    ](96%) Restarting services... \r'
  /bin/echo '[####################    ](96%) Restartings services... ' >>/var/log/jawaInstall.log 2>&1
  #  /bin/echo "Starting JAWA systemd services..."
  /bin/systemctl daemon-reload >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[#####################   ](97%) Restarting services... \r'
  /bin/echo '[#####################   ](97%) Restartings services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl reset-failed >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[######################  ](98%) Restarting services... \r'
  /bin/echo '[######################  ](98%) Restartings services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl enable jawa.service >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart jawa.service >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[####################### ](99%) Restarting services... \r'
  /bin/echo '[####################### ](99%) Restartings services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart nginx.service >>/var/log/jawaInstall.log 2>&1
  /bin/echo -ne '[########################](100%) Installation complete! \r'
  /bin/echo '[########################](100%) Restartings services... untini! ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1.5

  /usr/bin/clear

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
    /bin/echo "These aren't the droids you're looking for." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "You can go about your business." >>/var/log/jawaInstall.log 2>&1
    /bin/echo "Move along." >>/var/log/jawaInstall.log 2>&1
    #    /bin/sleep 3
    /bin/echo "JAWA removed." >>/var/log/jawaInstall.log 2>&1
  fi

}
cleaninstall() {
  /usr/bin/clear
  echo -ne '[#####                  ](25%) Backing up previously installed JAWA project \r'
  if [ -d "$installDir/jawa" ]; then
    timenow=$(date +%m-%d-%y_%T)
    /bin/mkdir -p $(pwd)/jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1
    if [ -d "$installDir/jawa/scripts" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the scripts $(pwd)/jawabackup-$timenow/"
      /bin/echo "[#####                  ](25%) Backing up the scripts $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/scripts" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1
    fi
    if [ -d "$installDir/jawa/resources" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the resources to $(pwd)/jawabackup-$timenow/"
      /bin/echo "[#####                  ](25%) Backing up the resources to $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/resources" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1
    fi
    if [ -d "$installDir/jawa/data" ]; then
      /usr/bin/clear
      /bin/echo -ne "[#####                  ](25%) Backing up the JAWA configuration files and logs to $(pwd)/jawabackup-$timenow/"
      /bin/echo "[#####                  ](25%) Backing up the JAWA configuration files and logs to $(pwd)/jawabackup-$timenow/" >>/var/log/jawaInstall.log 2>&1
      /bin/cp -r "$installDir/jawa/data" ./jawabackup-$timenow >>/var/log/jawaInstall.log 2>&1
    fi

    uninstall
  fi

}

displayMenu() {
  while true; do
    read -r -p "Please select from the following options:

1. Install
2. Cancel
 " opt
    case "$opt" in
    1)
      install
      ;;
    2)
      exit
      ;;
    *)
      /bin/echo "Please choose an option:(1, 2, 3, or 4):"
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
      /bin/echo "Please choose an option (1 or 2):"
      continue
      ;;
    esac
  done
}
selfsigned() {
  /bin/echo "Creating SSL cert" >>/var/log/jawaInstall.log 2>&1
  /usr/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 -subj "/C=US/ST=MN/L=Minneapolis/CN=jawa" -keyout "$installDir/jawa.key" -out "$installDir/jawa.crt" >>/var/log/jawaInstall.log 2>&1
  install
}

readme
displayMenu
