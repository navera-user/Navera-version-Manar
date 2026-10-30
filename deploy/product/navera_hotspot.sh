#!/usr/bin/env bash
#
# navera_hotspot.sh — the box's own Wi-Fi: phones and laptops join it (QR code on the access card,
# navera_tools/access_card.py) and open the web page at http://10.42.0.1:8181/.
#
#   navera_hotspot.sh --print     # the NetworkManager settings for the current env (no root)
#   sudo navera_hotspot.sh        # create / update the hotspot connection and bring it up
#   sudo navera_hotspot.sh --stop # take it down (the connection is kept, autoconnect off)
#
# Installed by deploy/install.sh --product as /usr/local/sbin/navera_hotspot.sh and run at boot
# by navera-hotspot.service. Settings from /etc/navera/navera.env (root-owned):
#   NAVERA_HOTSPOT           1 (default in product mode): on; 0: off
#   NAVERA_WIFI_SSID         network name (default NAVERA)
#   NAVERA_WIFI_PASSWORD     WPA2 password, 8-63 characters (default navera-iris)
#   NAVERA_WIFI_IFACE        the Wi-Fi interface (default: the first one NetworkManager lists)
#   NAVERA_WIFI_ADDRESS      the box's address on it (default 10.42.0.1/24; DHCP for the clients)
#   NAVERA_WIFI_CHANNEL      2.4 GHz channel (default 6)
# The hotspot uses the box's Wi-Fi card: the box can then not ALSO join another Wi-Fi network.
# No internet is needed: NAVERA and its page work offline.
# Captive portal: the hotspot's DNS answers every name with the box's address
# (/etc/NetworkManager/dnsmasq-shared.d/navera-portal.conf) and the firewall sends port 80 to the
# portal (navera_portal.py): a phone that joins opens NAVERA's page by itself.
# The firewall (navera_firewall.sh) opens DHCP, DNS and the portal on this interface only.
set -euo pipefail
MODE=apply
case "${1:-}" in
  --print) MODE=print ;; --stop) MODE=stop ;; "") ;;
  -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
esac
CON=navera-hotspot
SSID="${NAVERA_WIFI_SSID:-NAVERA}"
PASS="${NAVERA_WIFI_PASSWORD:-navera-iris}"
ADDR="${NAVERA_WIFI_ADDRESS:-10.42.0.1/24}"
CHAN="${NAVERA_WIFI_CHANNEL:-6}"

[[ "$SSID" =~ ^[A-Za-z0-9_.-]{1,32}$ ]] || { echo "NAVERA_WIFI_SSID: 1-32 letters, digits, _ . -" >&2; exit 2; }
[ "${#PASS}" -ge 8 ] && [ "${#PASS}" -le 63 ] || { echo "NAVERA_WIFI_PASSWORD: 8-63 characters (WPA2)" >&2; exit 2; }
[[ "$ADDR" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] || { echo "NAVERA_WIFI_ADDRESS: a.b.c.d/nn" >&2; exit 2; }
[[ "$CHAN" =~ ^([1-9]|1[0-3])$ ]] || { echo "NAVERA_WIFI_CHANNEL: 1-13" >&2; exit 2; }

iface() {
  [ -n "${NAVERA_WIFI_IFACE:-}" ] && { echo "$NAVERA_WIFI_IFACE"; return; }
  nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}'
}
settings() {   # the nmcli "connection modify" arguments (the password is not printed by --print)
  echo "802-11-wireless.mode ap 802-11-wireless.ssid $SSID 802-11-wireless.band bg"
  echo "802-11-wireless.channel $CHAN ipv4.method shared ipv4.addresses $ADDR ipv6.method disabled"
  echo "wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp"
  echo "connection.autoconnect yes connection.autoconnect-priority 100"
}

case "$MODE" in
  print)
    echo "connection $CON on $(iface || true) (password: ${#PASS} characters, not shown)"
    settings ;;
  stop)
    nmcli con modify "$CON" connection.autoconnect no 2>/dev/null || true
    nmcli con down "$CON" 2>/dev/null || true
    echo "hotspot $CON down" ;;
  apply)
    if [ "${NAVERA_HOTSPOT:-1}" = 0 ]; then echo "NAVERA_HOTSPOT=0: hotspot not started"; exit 0; fi
    dev=$(iface)
    [ -n "$dev" ] || { echo "no Wi-Fi interface found: hotspot not started" >&2; exit 1; }
    install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
    printf '# NAVERA captive portal (navera_hotspot.sh): every name -> the box\naddress=/#/%s\n' \
      "${ADDR%/*}" > /etc/NetworkManager/dnsmasq-shared.d/navera-portal.conf
    nmcli con show "$CON" >/dev/null 2>&1 || nmcli con add type wifi ifname "$dev" con-name "$CON" ssid "$SSID" >/dev/null
    # shellcheck disable=SC2046
    nmcli con modify "$CON" connection.interface-name "$dev" $(settings) wifi-sec.psk "$PASS"
    nmcli con up "$CON" >/dev/null
    echo "hotspot up: Wi-Fi '$SSID' on $dev, web page http://${ADDR%/*}:${NAVERA_WEB_PORT:-8181}/" ;;
esac
