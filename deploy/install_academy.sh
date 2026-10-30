#!/usr/bin/env bash
#
# install_academy.sh — install NAVERA Academy on a NAVERA box, beside NAVERA, fully offline.
#   sudo bash install_academy.sh --tarball /path/navera-academy-1.0.tar.gz [options]
#   bash install_academy.sh --root DIR --tarball FILE ...      # staged (no root): files under DIR only
#
# Options:
#   --tarball FILE        the release (FILE.sha256 next to it is checked)            [required]
#   --data-from DIR       where osm_sousse.mbtiles and models/ are copied from        [/home/shadow-team/academy-data]
#   --pyuser-from DIR     a pip --user base (DIR/lib/python3.X/site-packages: flask, torch, cv2…)
#                         copied to /opt/navera-academy/pyuser                         [/home/shadow-team/.local]
#   --new-teacher-password  give the teacher a new password even if the account exists
#   --no-start            install, but do not enable / start the service
#   --root DIR            staged install for tests: no user, no systemctl, no chown
#
# What it does (each step prints what it did):
#   1. checks the tarball's sha256
#   2. system user "academy" (home /var/lib/navera-academy, no login shell, groups video + render for the GPU)
#   3. code in /opt/navera-academy (read only, root-owned; the previous one kept as /opt/navera-academy.old)
#   4. Python packages in /opt/navera-academy/pyuser, data in /var/lib/navera-academy/data
#   5. /etc/navera-academy/academy.env (kept if it exists)
#   6. navera-academy.service (MemoryMax 1.5 GB, CPUWeight/IOWeight 10, Nice 10) + limits for the student
#      sandboxes (user-UID.slice) + linger for the academy user's systemd
#   7. the teacher account: password generated now, printed ONCE, stored only as a hash
#   8. NAVERA's firewall: 8300 added to NAVERA_FW_ALLOW_TCP in /etc/navera/navera.env (firewall reloaded)
#   9. the old development services (navera-academy as shadow-team, navera-netkeeper) replaced / disabled
#  10. service enabled and started; http://127.0.0.1:8300/ checked
set -euo pipefail

TARBALL=""; DATA_FROM="/home/shadow-team/academy-data"; PYUSER_FROM="/home/shadow-team/.local"
NEWPW=0; START=1; R=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tarball) shift; TARBALL="$1" ;;
    --data-from) shift; DATA_FROM="$1" ;;
    --pyuser-from) shift; PYUSER_FROM="$1" ;;
    --new-teacher-password) NEWPW=1 ;;
    --no-start) START=0 ;;
    --root) shift; R="$(realpath -m "$1")" ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$TARBALL" ] || { echo "--tarball FILE is required (--help)" >&2; exit 2; }
if [ -z "$R" ] && [ "$(id -u)" != 0 ]; then echo "run it with sudo (or --root DIR for a staged test)" >&2; exit 1; fi
say() { echo -e "\n== academy: $*"; }
staged() { [ -n "$R" ]; }

OPT="$R/opt/navera-academy"; VAR="$R/var/lib/navera-academy"; ETC="$R/etc/navera-academy"
UNITDIR="$R/etc/systemd/system"; NAVENV="$R/etc/navera/navera.env"

say "1. release check"
TARBALL="$(realpath "$TARBALL")"
[ -f "$TARBALL.sha256" ] || { echo "missing $TARBALL.sha256" >&2; exit 1; }
want="$(awk '{print $1}' "$TARBALL.sha256")"; have="$(sha256sum "$TARBALL" | awk '{print $1}')"
[ "$want" = "$have" ] || { echo "sha256 MISMATCH for $TARBALL" >&2; exit 1; }
echo "  sha256 OK ($have)"

say "2. system user academy"
if staged; then
  UID_A="$(id -u)"; echo "  (staged) user skipped, uid $UID_A used in the units"
else
  if ! id academy >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/navera-academy --no-create-home --shell /usr/sbin/nologin \
      --comment "NAVERA Academy" academy
    echo "  user academy created"
  fi
  for g in video render; do getent group "$g" >/dev/null && usermod -aG "$g" academy; done
  UID_A="$(id -u academy)"; echo "  academy uid $UID_A, groups: $(id -nG academy)"
fi

say "3. code in /opt/navera-academy"
mkdir -p "$(dirname "$OPT")"
rm -rf "$OPT.new"; mkdir -p "$OPT.new"
tar xzf "$TARBALL" -C "$OPT.new" --strip-components=1 --no-same-owner
[ -f "$OPT.new/server/app.py" ] || { echo "the tarball holds no server/app.py" >&2; exit 1; }
if [ -d "$OPT" ]; then
  [ -d "$OPT/pyuser" ] && mv "$OPT/pyuser" "$OPT.new/pyuser"       # keep the copied packages
  rm -rf "$OPT.old"; mv "$OPT" "$OPT.old"
fi
mv "$OPT.new" "$OPT"
staged || chown -R root:root "$OPT"
chmod -R go-w "$OPT"; chmod 755 "$OPT"
echo "  installed $(cat "$OPT/VERSION" 2>/dev/null || echo '?')"

say "4. Python packages and course data (offline: copied, never downloaded)"
if [ ! -d "$OPT/pyuser/lib" ]; then
  if [ -d "$PYUSER_FROM/lib" ]; then
    mkdir -p "$OPT/pyuser"; cp -a "$PYUSER_FROM/lib" "$OPT/pyuser/lib"
    find "$OPT/pyuser" -name '__pycache__' -prune -o -type f -name '*.pyc' -delete 2>/dev/null || true
    staged || chown -R root:root "$OPT/pyuser"
    echo "  packages copied from $PYUSER_FROM/lib ($(du -sh "$OPT/pyuser" | cut -f1))"
  else
    echo "  WARNING: no $PYUSER_FROM/lib: the Academy needs flask, flask_sock, torch, cv2… for the academy user"
  fi
else
  echo "  packages kept ($OPT/pyuser)"
fi
mkdir -p "$VAR"/{state,students,logs,data}
for f in osm_sousse.mbtiles models; do
  if [ -e "$VAR/data/$f" ]; then echo "  data kept: $f"
  elif [ -e "$DATA_FROM/$f" ]; then cp -a "$(realpath "$DATA_FROM/$f")" "$VAR/data/$f"; echo "  data copied: $f"
  else echo "  WARNING: $DATA_FROM/$f missing (map: missions 7, 8, 18, 21-24 and Sim Lite; models: mission 23)"; fi
done
if ! staged; then chown -R academy:academy "$VAR"; fi
chmod 750 "$VAR"

say "5. settings /etc/navera-academy/academy.env"
mkdir -p "$ETC"
if [ -f "$ETC/academy.env" ]; then echo "  kept"; else cp "$OPT/deploy/product/academy.env" "$ETC/academy.env"; echo "  written"; fi
chmod 644 "$ETC/academy.env"

say "6. systemd unit and resource limits"
mkdir -p "$UNITDIR" "$UNITDIR/user-$UID_A.slice.d" "$UNITDIR/user@$UID_A.service.d"
sed "s/@UID@/$UID_A/g" "$OPT/deploy/product/navera-academy.service" > "$UNITDIR/navera-academy.service"
sed "s/@UID@/$UID_A/g" "$OPT/deploy/product/user-slice-academy.conf" > "$UNITDIR/user-$UID_A.slice.d/50-navera-academy.conf"
sed "s/@UID@/$UID_A/g" "$OPT/deploy/product/user-service-academy.conf" > "$UNITDIR/user@$UID_A.service.d/50-navera-academy.conf"
if staged; then echo "  (staged) units written, linger skipped"
else
  loginctl enable-linger academy
  systemctl daemon-reload
  echo "  unit installed, linger on for academy"
fi

say "7. the teacher account"
run_manage() {
  if staged; then
    env ACADEMY_PRODUCT=1 ACADEMY_VAR="$VAR" ACADEMY_DATA="$VAR/data" ACADEMY_PYTHONUSERBASE="$OPT/pyuser" \
        PYTHONUSERBASE="$OPT/pyuser" PYTHONDONTWRITEBYTECODE=1 python3 "$OPT/server/manage.py" "$@"
  else
    runuser -u academy -- env HOME=/var/lib/navera-academy ACADEMY_PRODUCT=1 ACADEMY_VAR=/var/lib/navera-academy \
        ACADEMY_DATA=/var/lib/navera-academy/data PYTHONUSERBASE=/opt/navera-academy/pyuser \
        PYTHONDONTWRITEBYTECODE=1 python3 /opt/navera-academy/server/manage.py "$@"
  fi
}
if [ "$NEWPW" = 1 ] || ! grep -q '"teacher"' "$VAR/state/users.json" 2>/dev/null; then
  PW="$(run_manage teacher-password)"
  echo "  ┌──────────────────────────────────────────────────────────────"
  echo "  │ Teacher login:  teacher"
  echo "  │ Password:       $PW"
  echo "  │ Shown ONCE (only its hash is stored). Write it on the delivery sheet."
  echo "  └──────────────────────────────────────────────────────────────"
  unset PW
else
  echo "  the teacher account exists: password unchanged (--new-teacher-password for a new one)"
fi

say "8. NAVERA firewall: port 8300"
if [ -f "$NAVENV" ]; then
  cur="$(grep -E '^NAVERA_FW_ALLOW_TCP=' "$NAVENV" | tail -1 | cut -d= -f2- || true)"
  if echo ",${cur}," | tr -d ' "' | grep -q ',8300,'; then echo "  8300 already in NAVERA_FW_ALLOW_TCP"
  else
    new="$(echo "${cur:+$cur,}8300" | tr -d ' "')"
    tmp="$NAVENV.academy-tmp"
    if grep -qE '^NAVERA_FW_ALLOW_TCP=' "$NAVENV"; then
      awk -v v="$new" 'BEGIN{n=0} {l[NR]=$0; if (index($0, "NAVERA_FW_ALLOW_TCP=") == 1) n=NR}
           END{for (i=1;i<=NR;i++) print (i==n ? "NAVERA_FW_ALLOW_TCP=" v : l[i])}' "$NAVENV" > "$tmp"
    else
      { cat "$NAVENV"; printf 'NAVERA_FW_ALLOW_TCP=%s\n' "$new"; } > "$tmp"
    fi
    chmod --reference="$NAVENV" "$tmp"; staged || chown --reference="$NAVENV" "$tmp"
    mv -f "$tmp" "$NAVENV"
    echo "  NAVERA_FW_ALLOW_TCP=$new"
  fi
  if ! staged && systemctl is-enabled --quiet iris-firewall 2>/dev/null; then
    systemctl restart iris-firewall && echo "  firewall reloaded (iris-firewall)"
  fi
else
  echo "  WARNING: $NAVENV missing (install NAVERA first): port 8300 not added to the firewall"
fi

say "9. old development services"
if ! staged; then
  systemctl disable --now navera-netkeeper 2>/dev/null && echo "  navera-netkeeper disabled (NAVERA's own Wi-Fi setup is used)" || true
  rm -f /etc/NetworkManager/dnsmasq-shared.d/navera-captive.conf 2>/dev/null || true
fi

say "10. start"
if staged || [ "$START" = 0 ]; then
  echo "  (not started)"
else
  systemctl daemon-reload
  systemctl enable navera-academy.service >/dev/null 2>&1
  systemctl restart navera-academy.service
  ok=0
  for _ in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8300/ || true)"
    [ "$code" = 200 ] && { ok=1; break; }
    sleep 1
  done
  [ "$ok" = 1 ] && echo "  navera-academy answers on :8300" || { echo "  NOT answering: journalctl -u navera-academy -n 50"; exit 1; }
fi
host="$(hostname 2>/dev/null || echo navera-xxxx)"
echo
echo "NAVERA Academy: http://$host.local:8300/   (setup Wi-Fi: http://10.42.0.1:8300/)"
