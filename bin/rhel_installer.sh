#!/bin/bash

# Greetings, friends.  This installer is intended for Red Hat Enterprise Linux installations of JAWA.  #
# It will not work well for other operating systems.  Run with sudo, and may the force be with you.
#
#  usage: sudo bash /path/to/rhel_installer.sh
#
# What does this installer do?
# - installs python and a webapp
# - installs dependencies (see requirements.txt)
# - installs and configures nginx for hosting the webapp
# - creates a systemd unit file for running the JAWA service
# - creates a jawa service account on the server for running the webapp and managing cron
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
timenow=$(date +%m-%d-%y_%T)

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
*  Note: if upgrading from v2, choose the upgrade path /usr/local
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
       Please confirm [y|n]: " yn
    case $yn in
    [Yy]*)

      break
      ;;
    [Nn]*) read -r -p "Where would you like to install JAWA? [Press RETURN for $installDir]:  " new_dir ;;
    *) echo "Please answer yes or no." ;;
    esac
  done

  /usr/bin/clear
  echo -ne '[##                     ](10%) Reticulating splines... '
  echo '[##                     ](10%) Reticulating splines' >>/var/log/jawaInstall.log 2>&1
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
  /usr/bin/clear
  echo -ne '[######                  ](30%) Installing build tools from yum... '
  echo '[######                  ](30%) Installing build tools from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y -q epel-release build-essential git unzip zip nload tree >>/var/log/jawaInstall.log 2>&1 & spinner $! ""

  /usr/bin/clear
  /bin/echo -ne '[#######                ](35%) Installing nginx from yum... '
  /bin/echo '[#######                ](35%) Installing nginx... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y -q nginx >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  echo -ne '[########                ](40%) Installing python3-pip, python3-dev, and python3-venv from yum... '
  echo '[########                ](40%) Installing python3-pip, python3-dev, and python3-venv from yum...' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y -q python3-pip python3-dev python3-venv >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  #Python check
  /usr/bin/clear
  /bin/echo -ne '[########                ](42%) Safety check... '
  /bin/echo '[########                ](42%) Safety check ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1  & spinner $! ""
  if [ -e /usr/bin/python3 ]; then
    /bin/echo "Python 3 installed." >>/var/log/jawaInstall.log 2>&1
  else
    /bin/echo "Python 3 not present, please install Python3 with pip prior to installation"
    /bin/echo "Exiting..."
    exit 2
  fi

# change places!
  cd "$installDir"
  # cloning, like in that movie The Fly
  /usr/bin/clear
  /bin/echo -ne '[#########               ](45%) Cloning the JAWA project from GitHub... '
  /bin/echo '[#########               ](45%) Cloning the JAWA project from GitHub... ' >>/var/log/jawaInstall.log 2>&1
  git clone --branch develop https://github.com/jamf/JAWA.git jawa >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  # Restore backup?
  /usr/bin/clear
  /bin/echo -ne '[##########              ](50%) Checking for backups... '
  /bin/echo '[##########              ](50%) Checking for backups... ' >>/var/log/jawaInstall.log 2>&1
  /bin/sleep 1  & spinner $! ""
if [ -d "$currentDir/jawabackup-$timenow" ]; then
    while true; do
      /bin/echo ""
      read -p "Do you wish to restore your backup ($backupJAWA)  [y|n]: " yn
      case $yn in
      [Yy]*)
        if [ -d "$currentDir/jawabackup-$timenow/v2/" ]; then
          if [ -e "$currentDir/jawabackup-$timenow/v2/cron.json" ]; then
            /bin/echo "Migrating cron..."
            /bin/cp "$currentDir/jawabackup-$timenow/v2/cron.json" "$currentDir/jawabackup-$timenow/data/"
          fi
          if [ -e "$currentDir/jawabackup-$timenow/v2/webhook.conf" -o "$currentDir/jawabackup-$timenow/v2/jp_webhooks.json" ]; then
            /bin/echo "Migrating webhooks..."
            /usr/bin/python3 "$installDir/jawa/bin/v2_upgrade.py" "$currentDir/jawabackup-$timenow" >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
          fi
        fi
        /bin/cp -R "$currentDir/jawabackup-$timenow/data/" $installDir/jawa/
        /bin/cp -R "$currentDir/jawabackup-$timenow/resources/" $installDir/jawa/
        /bin/cp -R "$currentDir/jawabackup-$timenow/scripts/" $installDir/jawa/
        /bin/cp -R "$currentDir/jawabackup-$timenow/jawa_icon.png" $installDir/jawa/static/img/jawa_icon.png
        break
        ;;
      [Nn]*) break ;;
      *) echo "Please answer yes or no." ;;
      esac
    done
  fi
  # for gzip support in uwsgi
  #/usr/bin/yum install --no-install-recommends -y -q libpcre3-dev libz-dev

  # Stop the hackers
  /usr/bin/clear
  /bin/echo -ne '[###########             ](55%) Installing fail2ban from yum... '
  /bin/echo '[###########             ](55%) Installing fail2ban from yum... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install fail2ban -y -q >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
# For the bash inclined
  /usr/bin/clear
  /bin/echo -ne '[############            ](60%) Installing jq from yum... '
  /bin/echo '[############            ](60%) Installing jq from yum... ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/yum install -y -q jq >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  /bin/echo -ne '[#############           ](65%) Setting permissions for $installDir/jawa... '
  /bin/echo '[#############           ](65%) Setting permissions for $installDir/jawa ' >>/var/log/jawaInstall.log 2>&1
  chown -R jawa "$installDir/jawa" & spinner $! ""
  /usr/bin/clear
  /bin/echo -ne '[##############          ](70%) Enabling firewall and opening ports 22 & 443... '
  /bin/echo '[##############          ](70%) Enabling firewall and opening ports 22 & 443 ' >>/var/log/jawaInstall.log 2>&1
  /usr/bin/firewall-cmd --zone=public --add-port=443/tcp --permanent
  /usr/bin/firewall-cmd --zone=public --add-port=22/tcp --permanent
#  ufw allow 22 >>/var/log/jawaInstall.log 2>&1
#  ufw allow 443 >>/var/log/jawaInstall.log 2>&1
#  ufwStatus=$(ufw status | grep -i status)
#  if [ "$ufwStatus" != "Status: active" ]; then
#    /bin/echo ""
#    /bin/echo ""
#    /bin/echo ""
#    /bin/echo "NOTE: the OS firewall is being enabled, and ports 22 (SSH) and 443 (JAWA) are being opened inbound.
#    If you use another port for SSH you should enable ufw manually and allow your custom port before proceeding with the installation."
#    ufw enable
#  fi
  /usr/bin/clear
  # Create a venv for the app
  cd "$installDir/jawa"
  /usr/bin/clear
  /bin/echo -ne '[###############         ](75%) Creating venv... '
  /bin/echo '[###############         ](75%) Creating venv... ' >>/var/log/jawaInstall.log 2>&1
  python3 -m venv venv & spinner $! ""
  chown -R jawa "$installDir/jawa/venv"
  source "$installDir/jawa/venv/bin/activate"
  /usr/bin/clear
  /bin/echo -ne '[###############         ](75%) Upgrading pip and setuptools in venv... '
  /bin/echo '[###############         ](75%) Upgrading pip and setuptools in venv... ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install --upgrade pip setuptools >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  /usr/bin/clear
  /bin/echo -ne '[################        ](80%) pip installing support modules (httpie and glances) in venv... '
  /bin/echo '[################        ](80%) pip installing support modules (httpie and glances) in venv... ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install --upgrade httpie glances >>/var/log/jawaInstall.log 2>&1 & spinner $! ""
  # flask requirements
  /usr/bin/clear
  /bin/echo -ne '[#################       ](85%) pip installing jawa requirements.txt file in venv... '
  /bin/echo '[#################       ](85%) pip installing jawa requirements.txt file in venv... ' >>/var/log/jawaInstall.log 2>&1
  python -m pip install -r "$installDir/jawa/requirements.txt" >>/var/log/jawaInstall.log 2>&1 & spinner $! "" #
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
  # Creating the nginx site
#  if [ -e ${nginx_path}/jawa ]; then
#    rm -f ${nginx_enabled}/jawa
#    rm -f ${nginx_path}/jawa
#  fi
if [ -e /etc/nginx/nginx.conf ]; then
        /usr/bin/rm /etc/nginx/nginx.conf
    fi
    cat << EOF >> /etc/nginx/nginx.conf
# For more information on configuration, see:
#   * Official English Documentation: http://nginx.org/en/docs/
#   * Official Russian Documentation: http://nginx.org/ru/docs/

user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

# Load dynamic modules. See /usr/share/doc/nginx/README.dynamic.
include /usr/share/nginx/modules/*.conf;

events {
    worker_connections 1024;
}

http {
    log_format  main  '\$remote_addr - \$remote_user [\$time_local] "\$request" '
                      '\$status $body_bytes_sent "\$http_referer" '
                      '"\$http_user_agent" "\$http_x_forwarded_for"';
    fastcgi_buffers 8 16k;
    fastcgi_buffer_size 32k;
    access_log  /var/log/nginx/access.log  main;
    include /etc/nginx/sites-enabled/*;
    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    keepalive_timeout   65;
    types_hash_max_size 2048;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    # Load modular configuration files from the /etc/nginx/conf.d directory.
    # See http://nginx.org/en/docs/ngx_core_module.html#include
    # for more information.
    include /etc/nginx/conf.d/*.conf;


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
  /bin/systemctl enable jawa.service >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart jawa.service >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[######################  ](98%) Restarting services... \r'
  /bin/echo '[######################  ](98%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1
  /bin/systemctl restart firewalld >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[####################### ](99%) Restarting services... \r'
  /bin/echo '[####################### ](99%) Restarting services... ' >>/var/log/jawaInstall.log 2>&1

  /usr/bin/systemctl enable nginx.service >>/var/log/jawaInstall.log 2>&1
    /usr/bin/systemctl restart nginx.service >>/var/log/jawaInstall.log 2>&1
  /usr/sbin/setsebool -P httpd_can_network_connect 1 >>/var/log/jawaInstall.log 2>&1
  /usr/bin/clear
  /bin/echo -ne '[########################](100%) Installation complete! \r'
  /bin/echo '[########################](100%) Installation complete! untini! ' >>/var/log/jawaInstall.log 2>&1
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

("$@") &



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
  /usr/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 -subj "/C=US/ST=MN/L=Minneapolis/CN=jawa" -keyout "$installDir/jawa.key" -out "$installDir/jawa.crt" >>/var/log/jawaInstall.log 2>&1
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

readme
displayMenu
