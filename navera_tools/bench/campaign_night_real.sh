#!/bin/bash
# Night campaign on the screen bench with the real Insta360 (full 360 over USB): one
# night_screen.py run (~90 s) per condition, then the summary table.
#
#   navera_tools/bench/campaign_night_real.sh <output folder> [conditions...]
#
# Opens the camera and a full-screen window on DISPLAY :1 — run it only when the bench is
# free. The low-light visible run ("lowlight") is meant for a dark room: it is run last and
# the script pauses before it. Environment: NAVERA_MBTILES, NAVERA_STHN_DIR (navera_env.sh).
# Display imagery: Wayback 2022 (another date than the map) over Kalaa Kebira.
set -u
OUT=${1:?usage: campaign_night_real.sh <output folder> [conditions...]}
shift
cd "$(dirname "$0")/../.." || exit 1
mkdir -p "$OUT"
export DISPLAY=${DISPLAY:-:1}
AREA=${NIGHT_AREA:-$HOME/.navera_sim/bench_2026-10-06/wb2022}
LAT=${NIGHT_LAT:-35.8685}
LON=${NIGHT_LON:-10.5352}
SECONDS_PER_RUN=${NIGHT_SECONDS:-90}
CONDS=("$@")
if [ ${#CONDS[@]} -eq 0 ]; then
  CONDS=(clean crossover polarity fpn_nuc dead_pixels agc_jumps fog rain clouds hot_vehicles
         fires lights_drones birds wind worst lowlight)
fi
xset s off -dpms s noblank 2>/dev/null
for c in "${CONDS[@]}"; do
  if [ "$c" = "lowlight" ] && [ -t 0 ]; then
    read -r -p "low-light visible run next: darken the room, then press Enter " _
  fi
  echo "== $c"
  timeout $((SECONDS_PER_RUN + 300)) python3 navera_tools/bench/night_screen.py --source 360 \
    --condition "$c" --area "$AREA" --lat "$LAT" --lon "$LON" --seconds "$SECONDS_PER_RUN" \
    --save-frames "$OUT/frames_$c" --out "$OUT/$c.csv" > "$OUT/$c.log" 2>&1
  echo "   exit $?; $(tail -1 "$OUT/$c.log")"
  sleep 5                                   # the camera is released before the next run
done
python3 navera_tools/bench/night_screen_summary.py "$OUT" --md "$OUT/summary.md"
