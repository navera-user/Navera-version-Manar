#!/usr/bin/env bash
#
# provision_box.sh — set up ONE NAVERA box for delivery and write its record.
#
#   sudo deploy/provision_box.sh --serial NAV-0001 --customer "ACME Drones" \
#        [--lens FILE] [--camera-delay S] [--map-bundle DIR] [--env-extra FILE] [--root DIR]
#
# Run after deploy/install.sh, from the release directory. It:
#   1. writes the box identity to /etc/navera/box.env (serial, customer, release, date);
#   2. sets the live camera (NAVERA_CAMERA=live), installs the camera calibration (--lens, optional:
#      without it the lens is calibrated in flight) into /var/lib/navera and points navera.env at it,
#      and the bench-measured camera delay (--camera-delay, NAVERA_CAMERA_LATENCY_S);
#   3. sets the mission map package (--map-bundle) and any extra settings (--env-extra, KEY=VALUE lines);
#   4. runs the box checks (navera_tools/check_box.py) and writes the record
#      /var/lib/navera/provision/<serial>.json (+ a copy next to this script's release, if writable).
# Settings already in /etc/navera/navera.env are replaced key by key (a .bak is kept), never lost.
# --root DIR: do it under DIR instead of / (staged, no root needed; checks skipped).
set -euo pipefail

serial="" customer="" lens="" delay="" bundle="" extra="" R=""
while [ $# -gt 0 ]; do
    case "$1" in
        --serial) serial=$2; shift ;;
        --customer) customer=$2; shift ;;
        --lens) lens=$2; shift ;;
        --camera-delay) delay=$2; shift ;;
        --map-bundle) bundle=$2; shift ;;
        --env-extra) extra=$2; shift ;;
        --root) R=${2%/}; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
    shift
done
[[ "$serial" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "--serial is required (letters, digits, . _ -)" >&2; exit 2; }
[ -n "$customer" ] || { echo "--customer is required" >&2; exit 2; }
[ -z "$R" ] && [ "$(id -u)" -ne 0 ] && { echo "run with sudo (or --root DIR for a staged run)" >&2; exit 2; }

src=$(cd "$(dirname "$0")/.." && pwd)
env_file="$R/etc/navera/navera.env"
lib="$R/var/lib/navera"
mkdir -p "$R/etc/navera" "$lib/provision"
[ -f "$env_file" ] || cp "$src/deploy/navera.env.example" "$env_file"
cp -p "$env_file" "$env_file.bak"

set_env() {   # set_env KEY VALUE: replace or append one setting
    local k=$1 v=$2 tmp
    tmp=$(mktemp)
    grep -v -E "^[[:space:]]*#?[[:space:]]*${k}=" "$env_file" > "$tmp" || true
    printf '%s=%s\n' "$k" "$v" >> "$tmp"
    cat "$tmp" > "$env_file" && rm -f "$tmp"
}

release=$(head -n1 "$src/VERSION" 2>/dev/null || git -C "$src" describe --tags --always 2>/dev/null || echo unknown)
date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'NAVERA_BOX_SERIAL=%s\nNAVERA_BOX_CUSTOMER=%q\nNAVERA_BOX_RELEASE=%s\nNAVERA_BOX_PROVISIONED=%s\n' \
    "$serial" "$customer" "$release" "$date_utc" > "$R/etc/navera/box.env"

lens_sha=""
# a delivered box flies its real cameras (navera-discover finds them; the dev default replays samples)
set_env NAVERA_CAMERA live
if [ -n "$lens" ]; then
    [ -f "$lens" ] || { echo "no lens file $lens" >&2; exit 2; }
    dst="$lib/$(basename "$lens")"
    install -m 0644 "$lens" "$dst"
    set_env NAVERA_CAMERA_CALIBRATION "/var/lib/navera/$(basename "$lens")"
    lens_sha=$(sha256sum "$dst" | cut -d' ' -f1)
fi
if [ -n "$delay" ]; then
    [[ "$delay" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "--camera-delay must be seconds, e.g. 1.3" >&2; exit 2; }
    set_env NAVERA_CAMERA_LATENCY_S "$delay"
fi
if [ -n "$bundle" ]; then
    [ -d "$bundle" ] || { echo "no map bundle $bundle" >&2; exit 2; }
    # the package's own settings (DAY_DATASET_DIR, NAVERA_MBTILES, NAVERA_IERS_FILE, ...) for where it is now
    while IFS= read -r line; do
        [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]] && set_env "${line%%=*}" "${line#*=}"
    done < <(python3 "$src/navera_tools/mission_bundle.py" env "$bundle")
fi
if [ -n "$extra" ]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
        set_env "${line%%=*}" "${line#*=}"
    done < "$extra"
fi

checks="skipped (staged run)"
check_rc=0
if [ -z "$R" ]; then
    set +e
    # as the service user, with NAVERA's settings and the ROS workspace, as the services run
    out=$(mktemp)
    nhome=$(getent passwd navera | cut -d: -f6)
    (cd "$src" && runuser -u navera -- bash -c 'set -a; . /etc/navera/navera.env 2>/dev/null; set +a
        source /opt/ros/humble/setup.bash
        [ -f "$1/isaac_ros_common/install/setup.bash" ] && source "$1/isaac_ros_common/install/setup.bash"
        python3 navera_tools/check_box.py' _ "${nhome:-/home/navera}") >"$out" 2>&1
    check_rc=$?
    checks=$(tail -n 40 "$out"); rm -f "$out"
    set -e
fi

record="$lib/provision/$serial.json"
python3 - "$record" <<PY
import json, sys
rec = {"serial": "$serial", "customer": """$customer""", "release": "$release", "provisioned_utc": "$date_utc",
       "lens_file": "$(basename "${lens:-}")", "lens_sha256": "$lens_sha", "camera_delay_s": "$delay",
       "map_bundle": "$bundle", "check_box_rc": $check_rc, "check_box": """$(printf '%s' "$checks" | sed 's/"""/'"'"''"'"''"'"'/g')"""}
json.dump(rec, open(sys.argv[1], "w"), indent=1)
PY
echo "box $serial provisioned for $customer (release $release)"
echo "record: $record   check_box exit code: $check_rc"
[ "$check_rc" -eq 0 ] || echo "check_box reported problems: read the record, fix, run again"
