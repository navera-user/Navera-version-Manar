#!/bin/bash
# Undo install.sh:  sudo bash ~/navera-academy/setup/uninstall.sh   (keeps /etc/navera/setup.json)
set -u
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
systemctl disable --now navera-netkeeper.service navera-academy.service 2>/dev/null
rm -f /etc/systemd/system/navera-netkeeper.service /etc/systemd/system/navera-academy.service
rm -f /etc/NetworkManager/dnsmasq-shared.d/navera-captive.conf
nmcli connection delete navera-setup 2>/dev/null
systemctl daemon-reload
echo "removed (the academy can still be started by hand: ~/navera-academy/academy.sh start)"
