#!/usr/bin/env bash
# Real-camera celestial campaign on the screen bench: every screen-drawable sky/weather/obstacle condition
# x star limits 4 and 3 x three sky fields (rich, medium, sparse), then the table.
#
#   navera_tools/bench/campaign_celestial_real.sh OUT_FOLDER
#
# Before: dark room, camera in USB 'Android' mode, navera_tools/bench/lens_calib_screen.py --save done with the
# camera not moved since (~/.navera_sim/insta360_screen_pose.json names the lens it measured). ~15 min.
# Each field is its own run (its JSON is rewritten after every case, so a stop keeps what was measured).
set -u
OUT=${1:?usage: $0 OUT_FOLDER}
mkdir -p "$OUT"
cd "$(dirname "$0")/../.."
export PYTHONPATH=.:cn_pkg:navera_common:navera_tools/sim
CONDS="none,glow,twilight,haze,fog,cirrus,cirrus:2,clouds,clouds:1.5,moon,moon:0.3,moon_out,rain,dew,satellites,planes,drones,birds,insects,trees,noise,wind:0.2,wind:0.5,wind:1,wind:2,reflections,worst"
LIMITS="4,3"
# rich (Orion, 37/16 stars on the screen at mag 4/3), medium (Corvus-Virgo, 15/8), sparse (Pegasus, 17/7)
for FIELD in "88,7" "200,-20" "345,15"; do
    TAG=$(echo "$FIELD" | tr ',' '_')
    echo "=== field $FIELD ==="
    python3 navera_tools/bench/celestial_screen.py --fields "$FIELD" --limits "$LIMITS" --conditions "$CONDS" \
        --out "$OUT/celestial_screen_$TAG.json" 2>&1 | tee "$OUT/celestial_screen_$TAG.log"
done
python3 navera_tools/bench/summarise_celestial_screen.py "$OUT"/celestial_screen_*.json --md "$OUT/table.md"
