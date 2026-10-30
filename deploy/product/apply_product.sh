#!/usr/bin/env bash
#
# apply_product.sh — turn an installed NAVERA box into a delivered product box.
# Run by deploy/install.sh --product (or NAVERA_PRODUCT_MODE=1); by hand:
#   sudo deploy/product/apply_product.sh [--dry-run]
#   deploy/product/apply_product.sh --root DIR     # staged (no root): files under DIR only
#
# Steps (deploy/README.md §13):
#   1. NAVERA_PRODUCT_MODE=1 in /etc/navera/navera.env; a web control token generated when
#      NAVERA_WEB_TOKEN is empty (control then always needs it)
#   2. SSH: NAVERA_PRODUCT_SSH=keys (default): keys only (no password, no root login) —
#      refused when no account has ~/.ssh/authorized_keys (it would lock everyone out;
#      NAVERA_PRODUCT_SSH_FORCE=1 overrides); off: the SSH server disabled
#   3. the developer sudo rules: files of /etc/sudoers.d granting NOPASSWD (other than
#      navera-web, the web page's exact restart commands) moved to /var/backups/navera-sudoers
#   4. the firewall (navera_firewall.sh, iris-firewall.service)
#   5. services a sealed box does not use disabled (NAVERA_PRODUCT_DISABLE to choose)
#   6. filesystem power-cut settings (deploy/setup_fs.sh: fsck.repair=yes)
#   7. access: the box joins the client's Wi-Fi when it can, else raises its setup Wi-Fi (the same
#      name and password on every box: the access card's QR code) whose setup page puts it on the
#      client's Wi-Fi (navera_wifi.py, navera_hotspot.sh, navera_portal.py); hostname navera
#      (http://navera.local:8181/); control without the code from those networks
#   8. IRIS maintenance VPN (Tailscale), when NAVERA_TAILSCALE_AUTHKEY is given — deploy/README.md §14
# The desktop is turned off by install.sh itself (--product implies --headless).
# Every step says what it did; undo commands: deploy/README.md §13.4.
set -euo pipefail
SRC="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
DRY=0; R="${DESTDIR:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --root) shift; R="$1" ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$R" ] && R="$(realpath -m "$R")"
if [ "$DRY" = 0 ] && [ -z "$R" ] && [ "$(id -u)" != 0 ]; then echo "run it with sudo" >&2; exit 1; fi
say() { echo -e "\n== product: $*"; }
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else "$@"; fi; }
skip() { echo "  (staged in $R: skipped) $*"; }
if [ -n "$R" ]; then SYSTEMCTL=(systemctl --root="$R"); else SYSTEMCTL=(systemctl); fi
ENV="$R/etc/navera/navera.env"
[ -f "$ENV" ] || { echo "$ENV missing: run deploy/install.sh first" >&2; exit 1; }
getenv() { grep -E "^$1=" "$ENV" | tail -1 | cut -d= -f2- || true; }
setenv() {   # setenv KEY VALUE: replace the last KEY= line, or append it (atomic, mode kept)
  [ "$DRY" = 1 ] && { echo "  + set $1 in $ENV"; return; }
  local tmp="$ENV.navera-tmp"
  if grep -qE "^$1=" "$ENV"; then
    awk -v k="$1" -v v="$2" 'BEGIN{n=0} {l[NR]=$0; if (index($0, k "=") == 1) n=NR} END{for (i=1;i<=NR;i++) print (i==n ? k "=" v : l[i])}' "$ENV" > "$tmp"
  else
    { cat "$ENV"; printf '%s=%s\n' "$1" "$2"; } > "$tmp"
  fi
  chmod --reference="$ENV" "$tmp"; [ -z "$R" ] && chown --reference="$ENV" "$tmp"
  sync "$tmp" 2>/dev/null || sync; mv -f "$tmp" "$ENV"
}

say "1. product mode and web control token"
setenv NAVERA_PRODUCT_MODE 1
if [ -z "$(getenv NAVERA_WEB_TOKEN)" ]; then
  setenv NAVERA_WEB_TOKEN "$(openssl rand -hex 16)"
  echo "  NAVERA_WEB_TOKEN generated (read it with: sudo grep NAVERA_WEB_TOKEN /etc/navera/navera.env)"
else
  echo "  NAVERA_WEB_TOKEN already set: kept"
fi
[ -z "$(getenv NAVERA_WEB_HOST)" ] && echo "  NOTE: NAVERA_WEB_HOST empty: the web page listens on every network" \
  "(the firewall below still applies); set iface:<vehicle interface> or localhost to narrow it"

say "2. SSH"
SSH_MODE="${NAVERA_PRODUCT_SSH:-$(getenv NAVERA_PRODUCT_SSH)}"; SSH_MODE="${SSH_MODE:-keys}"
case "$SSH_MODE" in
  keys)
    if [ -z "$R" ] && [ "${NAVERA_PRODUCT_SSH_FORCE:-0}" != 1 ] && \
       ! ls /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys >/dev/null 2>&1; then
      echo "  REFUSED: no ~/.ssh/authorized_keys on this box: keys-only SSH would lock everyone out." >&2
      echo "  Copy a key first (ssh-copy-id <user>@<box>), or NAVERA_PRODUCT_SSH=off, or NAVERA_PRODUCT_SSH_FORCE=1." >&2
      exit 1
    fi
    run install -d -m 0755 "$R/etc/ssh/sshd_config.d"
    run install -m 0644 "$SRC/deploy/product/sshd-navera-product.conf" "$R/etc/ssh/sshd_config.d/10-navera-product.conf"
    if [ -n "$R" ]; then skip "sshd -t && systemctl reload ssh"
    else run sshd -t && run systemctl reload ssh.service || echo "  WARNING: ssh not reloaded (sshd -t failed?)"; fi
    setenv NAVERA_PRODUCT_SSH keys
    echo "  SSH: keys only, no password, no root login" ;;
  off)
    run "${SYSTEMCTL[@]}" disable ssh.service ssh.socket 2>/dev/null || true
    [ -z "$R" ] && { run systemctl stop ssh.service ssh.socket 2>/dev/null || true; }
    setenv NAVERA_PRODUCT_SSH off
    echo "  SSH: disabled (maintenance: local console, or re-enable: sudo systemctl enable --now ssh)" ;;
  *) echo "  NAVERA_PRODUCT_SSH=$SSH_MODE: keys or off" >&2; exit 2 ;;
esac

say "3. developer sudo rules (NOPASSWD) removed; navera-web kept"
BK="$R/var/backups/navera-sudoers"
moved=0
for f in "$R"/etc/sudoers.d/*; do
  [ -f "$f" ] || continue
  case "$(basename "$f")" in navera-web|README) continue ;; esac
  if grep -qE '^[^#]*NOPASSWD' "$f" 2>/dev/null; then
    run install -d -m 0700 "$BK"; run mv -f "$f" "$BK/"; moved=$((moved + 1))
    echo "  moved $(basename "$f") to $BK (restore: sudo mv $BK/$(basename "$f") /etc/sudoers.d/)"
  fi
done
[ "$moved" = 0 ] && echo "  none found"
if [ -z "$R" ] && [ "$DRY" = 0 ] && ! visudo -c -q; then
  echo "  sudoers check FAILED after the move: restoring" >&2
  mv -f "$BK"/* /etc/sudoers.d/ 2>/dev/null; exit 1
fi

say "4. firewall (iris-firewall.service)"
run install -d -m 0755 "$R/usr/local/sbin" "$R/etc/systemd/system"
run install -m 0755 "$SRC/deploy/product/navera_firewall.sh" "$R/usr/local/sbin/navera_firewall.sh"
run install -m 0644 "$SRC/deploy/product/iris-firewall.service" "$R/etc/systemd/system/iris-firewall.service"
if [ "$DRY" = 0 ]; then
  ( set -a; . "$ENV"; set +a; "$SRC/deploy/product/navera_firewall.sh" --check ) \
    || { echo "  firewall rules do not load: not enabled" >&2; exit 1; }
fi
if [ -n "$R" ]; then
  run "${SYSTEMCTL[@]}" enable iris-firewall.service; skip "systemctl daemon-reload; systemctl restart iris-firewall"
else
  run systemctl daemon-reload; run systemctl enable iris-firewall.service; run systemctl restart iris-firewall.service
fi

say "5. unused services disabled"
DISABLE="${NAVERA_PRODUCT_DISABLE:-$(getenv NAVERA_PRODUCT_DISABLE)}"
DISABLE="${DISABLE:-bluetooth.service ModemManager.service cups.service cups-browsed.service kerneloops.service whoopsie.service apport.service apport-autoreport.path apport-forward.socket rpcbind.service rpcbind.socket unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer fwupd-refresh.timer}"
for s in $DISABLE; do
  if [ -n "$R" ]; then
    [ -e "$R/etc/systemd/system/$s" ] || [ -e "$R/lib/systemd/system/$s" ] || continue
    run "${SYSTEMCTL[@]}" disable "$s" >/dev/null 2>&1 || true; echo "  disabled $s"
  elif [ -n "$(systemctl list-unit-files --no-legend "$s" 2>/dev/null)" ]; then
    run systemctl disable --now "$s" >/dev/null 2>&1 || true; echo "  disabled $s"
  fi
done

say "6. filesystem settings for power cuts"
FS_ARGS=(); [ "$DRY" = 1 ] && FS_ARGS+=(--dry-run); [ -n "$R" ] && FS_ARGS+=(--root "$R")
"$SRC/deploy/setup_fs.sh" "${FS_ARGS[@]}" || echo "  WARNING: deploy/setup_fs.sh reported a FAIL (see above)"

say "7. access: Wi-Fi (client network or setup hotspot), setup page, access card"
[ -z "$(getenv NAVERA_HOTSPOT)" ] && setenv NAVERA_HOTSPOT 1
[ -z "$(getenv NAVERA_WIFI_SSID)" ] && setenv NAVERA_WIFI_SSID NAVERA
[ -z "$(getenv NAVERA_WIFI_PASSWORD)" ] && setenv NAVERA_WIFI_PASSWORD navera-iris
# control without the code only from the box's own setup hotspot (its subnet, while it is up);
# a client Wi-Fi ("wifi") or the maintenance VPN (100.64.0.0/10) is trusted only when set by hand
[ -z "$(getenv NAVERA_WEB_TRUST_NETS)" ] && setenv NAVERA_WEB_TRUST_NETS "hotspot"
run install -d -m 0755 "$R/usr/local/lib/navera"
run install -m 0755 "$SRC/deploy/product/navera_hotspot.sh" "$R/usr/local/sbin/navera_hotspot.sh"
run install -m 0755 "$SRC/deploy/product/navera_wifi.py" "$R/usr/local/lib/navera/navera_wifi.py"
run install -m 0755 "$SRC/deploy/product/navera_portal.py" "$R/usr/local/lib/navera/navera_portal.py"
if [ -n "$R" ]; then run install -d -m 1770 "$R/var/lib/navera/wifi"
else run install -d -m 1770 -o root -g navera /var/lib/navera/wifi; fi
for u in navera-wifi navera-portal; do
  run install -m 0644 "$SRC/deploy/product/$u.service" "$R/etc/systemd/system/$u.service"
done
HOST="${NAVERA_HOSTNAME:-navera}"
if [ -n "$R" ]; then
  run "${SYSTEMCTL[@]}" enable navera-wifi.service navera-portal.service
  skip "hostnamectl set-hostname $HOST; systemctl restart iris-firewall navera-wifi navera-portal; access card"
else
  [ "$(hostname)" = "$HOST" ] || run hostnamectl set-hostname "$HOST"
  run systemctl daemon-reload
  run systemctl enable navera-wifi.service navera-portal.service
  run systemctl restart iris-firewall.service navera-portal.service
  run systemctl restart navera-wifi.service || echo "  WARNING: navera-wifi not started (journalctl -u navera-wifi)"
  if [ "$DRY" = 0 ]; then
    python3 "$SRC/navera_tools/access_card.py" --env "$ENV" --out /var/lib/navera/access_card \
      || echo "  WARNING: access card not made (python3 navera_tools/access_card.py --out DIR)"
  fi
fi
echo "  on the client's Wi-Fi: http://$HOST.local:8181/ ; setup Wi-Fi '$(getenv NAVERA_WIFI_SSID)' when not connected"

say "8. IRIS maintenance (Tailscale): only when NAVERA_TAILSCALE_AUTHKEY is given for this run"
if [ -n "${NAVERA_TAILSCALE_AUTHKEY:-}" ] && [ -z "$R" ]; then
  if command -v tailscale >/dev/null; then
    run tailscale up --auth-key "$NAVERA_TAILSCALE_AUTHKEY" --hostname "$HOST-$(cut -c1-8 /etc/machine-id)" --ssh \
      && echo "  on IRIS's tailnet as $HOST-$(cut -c1-8 /etc/machine-id) (the key is not stored)" \
      || echo "  WARNING: tailscale up failed (internet? key?)"
  else
    echo "  tailscale not installed: install it first (deploy/README.md §14)"
  fi
else
  echo "  skipped (sudo NAVERA_TAILSCALE_AUTHKEY=tskey-... apply_product.sh to enrol the box)"
fi

say "done (product box)"
