#!/bin/bash
# NAVERA Academy — install the automatic start and the Wi-Fi setup (run ONCE, with sudo):
#     sudo bash ~/navera-academy/setup/install.sh
# Installs: navera-academy.service (the academy, at every power-on), navera-netkeeper.service
# (setup Wi-Fi "NAVERA-Setup-XXXX" when no known Wi-Fi), the captive address for the setup Wi-Fi,
# and /etc/navera/setup.json (this device's setup Wi-Fi name and password). Reversible: uninstall.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0"; exit 1; }
SETUP="$(cd "$(dirname "$0")" && pwd)"
ACADEMY="$(dirname "$SETUP")"
OWNER="$(stat -c %U "$ACADEMY")"
OWNER_UID="$(id -u "$OWNER")"

# 1. this device's setup Wi-Fi name and password (kept if they already exist)
mkdir -p /etc/navera
if [ ! -f /etc/navera/setup.json ]; then
  MAC=$(cat /sys/class/net/$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')/address | tr -d ':' | tr a-z A-Z)
  PW=$(python3 -c "import secrets; print(''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(10)))")
  printf '{"ssid": "NAVERA-Setup-%s", "password": "%s", "public_url": ""}\n' "${MAC: -4}" "$PW" > /etc/navera/setup.json
  chmod 644 /etc/navera/setup.json
fi

# 2. on the setup Wi-Fi every name points to this device (the setup page opens by itself)
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" > /etc/NetworkManager/dnsmasq-shared.d/navera-captive.conf

# 3. the academy starts at every power-on, as $OWNER (its sandboxes need the user's systemd)
loginctl enable-linger "$OWNER"
cat > /etc/systemd/system/navera-academy.service <<UNIT
[Unit]
Description=NAVERA Academy dashboard
After=network.target user@$OWNER_UID.service
Wants=user@$OWNER_UID.service

[Service]
User=$OWNER
WorkingDirectory=$ACADEMY/server
Environment=XDG_RUNTIME_DIR=/run/user/$OWNER_UID
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$OWNER_UID/bus
ExecStart=/usr/bin/python3 $ACADEMY/server/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

# 4. the network keeper (needs root to change the Wi-Fi)
cat > /etc/systemd/system/navera-netkeeper.service <<UNIT
[Unit]
Description=NAVERA network keeper (Wi-Fi setup without cables)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
ExecStart=/usr/bin/python3 $SETUP/netkeeper.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
# the academy may already run by hand: stop that copy so the service owns port 8300
sudo -u "$OWNER" "$ACADEMY/academy.sh" stop >/dev/null 2>&1 || true
systemctl enable --now navera-academy.service navera-netkeeper.service
sleep 3
systemctl --no-pager --lines=0 status navera-academy.service navera-netkeeper.service | grep -E "●|Active"
echo
echo "Setup Wi-Fi of this device: $(python3 -c "import json;c=json.load(open('/etc/navera/setup.json'));print(c['ssid'],' password:',c['password'])")"
echo "Print the sticker: python3 $SETUP/make_sticker.py"
