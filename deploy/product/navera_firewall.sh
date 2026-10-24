#!/usr/bin/env bash
#
# navera_firewall.sh — the delivered box's firewall: incoming traffic is dropped except what
# NAVERA is configured to receive. Outgoing traffic is free (NAVERA connects out to network
# GPS, the autopilot, NTP). iptables / ip6tables (the Jetson L4T kernel has no nftables
# conntrack, CONFIG_NFT_CT unset): one chain NAVERA-IN, jumped to first from INPUT; the other
# rules on the box (Docker's) are left as they are.
#
#   navera_firewall.sh --print      # the IPv4 and IPv6 rules for the current settings (no root)
#   navera_firewall.sh --check      # the rules load (in a user + network namespace: no root)
#   sudo navera_firewall.sh         # apply (the chain is replaced in one iptables-restore)
#   sudo navera_firewall.sh --stop  # remove the chain (everything open again)
#
# Installed by deploy/install.sh --product as /usr/local/sbin/navera_firewall.sh (root-owned)
# and run at boot by iris-firewall.service. Settings come from /etc/navera/navera.env ONLY
# (root-owned: never the files the navera user can write):
#   NAVERA_WEB_PORT          the web page (default 8181), TCP
#   NAVERA_PRODUCT_SSH       keys (default): TCP 22 open; off: closed
#   NAVERA_VEHICLE_MAVLINK_URL, NAVERA_MAVLINK_URL
#                            a listening MAVLink port (udpin:/udp:/tcpin:<ip>:<port>) is opened
#   ROS_LOCALHOST_ONLY, ROS_DOMAIN_ID
#                            ROS 2 on the network (LOCALHOST_ONLY not 1): the DDS ports of that
#                            domain (UDP 7400+250*id .. +249), all domains for ROS_DOMAIN_ID=auto
#   NAVERA_FW_ALLOW_TCP / NAVERA_FW_ALLOW_UDP   more ports or ranges, comma-separated (5600, 9000-9010)
#   NAVERA_FW_ALLOW_FROM     restrict all the above to these sources (comma-separated
#                            addresses / CIDR, IPv4 or IPv6: the vehicle network); empty = any
# Always allowed: loopback, replies to NAVERA's own connections, ICMP echo, ICMPv6 (neighbour
# discovery: IPv6 link-local cameras), DHCP replies.
set -euo pipefail
MODE=apply
case "${1:-}" in
  --print) MODE=print ;; --check) MODE=check ;; --stop) MODE=stop ;; "") ;;
  -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
esac

ports() {   # ports "a,b c" → validated port numbers / ranges, comma-separated
  local out=() p
  for p in ${1//,/ }; do
    [[ "$p" =~ ^[0-9]{1,5}(-[0-9]{1,5})?$ ]] || { echo "navera_firewall: ignored port '$p'" >&2; continue; }
    out+=("$p")
  done
  (IFS=,; echo "${out[*]}")
}
listen_port() {   # MAVLink URL → "udp PORT" / "tcp PORT" when NAVERA listens on it
  case "$1" in
    udpin:*:*|udp:*:*) echo "udp ${1##*:}" ;;
    tcpin:*:*) echo "tcp ${1##*:}" ;;
  esac
}

tcp="${NAVERA_WEB_PORT:-8181}"
[ "${NAVERA_PRODUCT_SSH:-keys}" = off ] || tcp="$tcp,22"
udp=""
for url in "${NAVERA_VEHICLE_MAVLINK_URL:-}" "${NAVERA_MAVLINK_URL:-}"; do
  read -r proto port <<<"$(listen_port "$url")" || true
  [ -n "${port:-}" ] && { [ "$proto" = tcp ] && tcp="$tcp,$port" || udp="$udp,$port"; }
  port=""
done
if [ "${ROS_LOCALHOST_ONLY:-0}" != 1 ]; then
  if [[ "${ROS_DOMAIN_ID:-0}" =~ ^[0-9]+$ ]]; then
    b=$((7400 + 250 * ${ROS_DOMAIN_ID:-0})); udp="$udp,$b-$((b + 249))"
  else
    udp="$udp,7400-65535"                 # auto: the domain of a vehicle found at boot
  fi
fi
tcp=$(ports "$tcp,${NAVERA_FW_ALLOW_TCP:-}"); udp=$(ports "${udp#,},${NAVERA_FW_ALLOW_UDP:-}")

v4=(); v6=()
allow_from="${NAVERA_FW_ALLOW_FROM:-}"
for s in ${allow_from//,/ }; do
  if [[ "$s" == *:* ]] && [[ "$s" =~ ^[0-9A-Fa-f:]+(/[0-9]{1,3})?$ ]]; then v6+=("$s")
  elif [[ "$s" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?$ ]]; then v4+=("$s")
  else echo "navera_firewall: ignored source '$s'" >&2; fi
done
rules() {   # rules <4|6> <tcp|udp> <ports> → accept lines (per source when restricted)
  local fam=$1 proto=$2 list=${3//-/:} src
  [ -n "$list" ] || return 0
  local srcs=()
  if [ ${#v4[@]} -gt 0 ] || [ ${#v6[@]} -gt 0 ]; then
    if [ "$fam" = 4 ]; then srcs=(${v4[@]+"${v4[@]}"}); else srcs=(${v6[@]+"${v6[@]}"}); fi
    for src in ${srcs[@]+"${srcs[@]}"}; do
      echo "-A NAVERA-IN -s $src -p $proto -m multiport --dports $list -j ACCEPT"
    done
  else
    echo "-A NAVERA-IN -p $proto -m multiport --dports $list -j ACCEPT"
  fi
}

ruleset() {   # ruleset <4|6>  → iptables-restore input
  echo "# NAVERA product firewall (deploy/product/navera_firewall.sh) — generated, do not edit"
  echo "*filter"
  echo ":NAVERA-IN - [0:0]"
  echo "-F NAVERA-IN"
  echo "-A NAVERA-IN -i lo -j ACCEPT"
  echo "-A NAVERA-IN -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
  echo "-A NAVERA-IN -m conntrack --ctstate INVALID -j DROP"
  if [ "$1" = 4 ]; then
    echo "-A NAVERA-IN -p icmp --icmp-type echo-request -j ACCEPT"
    echo "-A NAVERA-IN -p udp --sport 67 --dport 68 -j ACCEPT"
  else
    echo "-A NAVERA-IN -p ipv6-icmp -j ACCEPT"
    echo "-A NAVERA-IN -p udp --sport 547 --dport 546 -j ACCEPT"
  fi
  rules "$1" tcp "$tcp"
  rules "$1" udp "$udp"
  echo "-A NAVERA-IN -j DROP"
  echo "COMMIT"
}

load() {   # load <4|6> : the chain, then the jump from INPUT (once, first)
  local ipt=iptables; [ "$1" = 6 ] && ipt=ip6tables
  ruleset "$1" | "$ipt-restore" --noflush
  "$ipt" -C INPUT -j NAVERA-IN 2>/dev/null || "$ipt" -I INPUT 1 -j NAVERA-IN
}

summary="tcp ${tcp:-none}; udp ${udp:-none}; from ${allow_from:-any}"
case "$MODE" in
  print) echo "## IPv4"; ruleset 4; echo "## IPv6"; ruleset 6 ;;
  check) lock=$(mktemp); trap 'rm -f "$lock"' EXIT
         export XTABLES_LOCKFILE="$lock"
         export -f ruleset rules load; export tcp udp
         v4s="${v4[*]:-}" v6s="${v6[*]:-}" unshare -rn bash -c \
           'v4=($v4s); v6=($v6s); set -e; load 4; load 6; iptables -S NAVERA-IN >/dev/null' \
           && echo "firewall rules OK ($summary)" ;;
  stop)  for ipt in iptables ip6tables; do
           while "$ipt" -D INPUT -j NAVERA-IN 2>/dev/null; do :; done
           "$ipt" -F NAVERA-IN 2>/dev/null || true; "$ipt" -X NAVERA-IN 2>/dev/null || true
         done; echo "firewall off" ;;
  apply) load 4; load 6; echo "firewall on: $summary" ;;
esac
