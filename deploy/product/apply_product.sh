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
#   7. access: the box's own Wi-Fi (navera_hotspot.sh, NAVERA_HOTSPOT=1), the access gate and the
#      public link (navera_access_gate.py, navera_remote.sh; NAVERA_REMOTE_KEY generated), and
#      the printable access card (navera_tools/access_card.py) — deploy/README.md §14
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
DISABLE="${DISABLE:-avahi-daemon.service avahi-daemon.socket bluetooth.service ModemManager.service cups.service cups-browsed.service kerneloops.service whoopsie.service apport.service apport-autoreport.path apport-forward.socket rpcbind.service rpcbind.socket unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer fwupd-refresh.timer}"
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

say "7. access: hotspot, access gate, public link, access card"
[ -z "$(getenv NAVERA_HOTSPOT)" ] && setenv NAVERA_HOTSPOT 1
[ -z "$(getenv NAVERA_WIFI_SSID)" ] && setenv NAVERA_WIFI_SSID NAVERA
[ -z "$(getenv NAVERA_WIFI_PASSWORD)" ] && setenv NAVERA_WIFI_PASSWORD navera-iris
if [ -z "$(getenv NAVERA_REMOTE_KEY)" ]; then
  setenv NAVERA_REMOTE_KEY "$(openssl rand -hex 12)"; echo "  NAVERA_REMOTE_KEY generated (it is on the access card)"
else
  echo "  NAVERA_REMOTE_KEY already set: kept"
fi
run install -d -m 0755 "$R/usr/local/lib/navera"
run install -m 0755 "$SRC/deploy/product/navera_hotspot.sh" "$R/usr/local/sbin/navera_hotspot.sh"
run install -m 0755 "$SRC/deploy/product/navera_remote.sh" "$R/usr/local/sbin/navera_remote.sh"
run install -m 0755 "$SRC/deploy/product/navera_access_gate.py" "$R/usr/local/lib/navera/navera_access_gate.py"
for u in navera-hotspot navera-portal navera-access-gate navera-remote; do
  run install -m 0644 "$SRC/deploy/product/$u.service" "$R/etc/systemd/system/$u.service"
done
if [ -n "$R" ]; then
  run "${SYSTEMCTL[@]}" enable navera-hotspot.service navera-portal.service navera-access-gate.service navera-remote.service
  skip "systemctl restart iris-firewall navera-hotspot navera-access-gate navera-remote; access card"
else
  run systemctl daemon-reload
  run systemctl enable navera-hotspot.service navera-portal.service navera-access-gate.service navera-remote.service
  run systemctl restart iris-firewall.service
  run systemctl restart navera-hotspot.service || echo "  WARNING: hotspot not started (see: journalctl -u navera-hotspot)"
  run systemctl restart navera-portal.service navera-access-gate.service
  run systemctl restart navera-remote.service || echo "  NOTE: no public link yet (Tailscale not logged in: deploy/README.md §14)"
  if [ "$DRY" = 0 ]; then
    ( set -a; . "$ENV"; set +a; python3 "$SRC/navera_tools/access_card.py" --env "$ENV" --out /var/lib/navera/access_card ) \
      && chmod -R go-rwx /var/lib/navera/access_card \
      || echo "  WARNING: access card not made (python3 navera_tools/access_card.py --out DIR)"
  fi
fi

say "done (product box)"
