#!/bin/bash
# Day vision on the REAL camera (Insta360 360 over USB) facing the bench screen: every screen
# condition at two strengths and two speeds, plus a clear baseline and a combined worst case.
# Each run: 90 s, GPS good 0-30 s, drifting (spoofed, 3 m/s) 30-55 s, lost after.
#
#   navera_tools/bench/campaign_day_real.sh <out_dir> [kinds] [amounts] [speeds]
#     kinds   comma list (default: all screen_overlays.KINDS)
#     amounts comma list (default 0.3,0.7); speeds comma list, m/s (default 20,60)
#   then: python3 navera_tools/bench/summarise_day_real.py <out_dir>
#
# Needs the camera and the screen (DISPLAY): run by the operator, one domain at a time.
# ~76 runs x ~100 s = ~2 h 10 min for the full set; a run that fails is logged and skipped.
set -u
OUT=${1:?usage: campaign_day_real.sh <out_dir> [kinds] [amounts] [speeds]}
KINDS=${2:-clouds,cloudshadow,haze,fog,dust,smoke,rain,heavyrain,snow,glare,flare,dusk,night,birds,planes,drones,insects,wind}
AMOUNTS=${3:-0.3,0.7}
SPEEDS=${4:-20,60}
cd "$(dirname "$0")/../.." || exit 1
mkdir -p "$OUT"
export PYTHONPATH=.:day_pkg:navera_common:cn_pkg
BASE=(python3 -u navera_tools/bench/screen_flight.py --source 360 --area "$HOME/.navera_sim/bench_2026-10-06/area"
      --lat 35.82227 --lon 10.61691 --seconds 90 --gps-drift-at 30 --gps-lost-at 55 --matcher sift --height 1500)

run() {   # run <name> <speed> <overlay> <amount>
  local name=$1 speed=$2 ov=$3 amt=$4
  local csv="$OUT/${name}_v${speed}.csv"
  if [ -s "$csv" ]; then echo "skip $name v$speed (done)"; return; fi
  echo "=== $(date +%H:%M:%S) $name speed $speed overlay $ov amount $amt"
  timeout 300 "${BASE[@]}" --speed "$speed" --overlay "$ov" --overlay-amount "$amt" --out "$csv" \
    > "$OUT/${name}_v${speed}.log" 2>&1 || echo "    FAILED (exit $?), see $OUT/${name}_v${speed}.log"
  tail -6 "$OUT/${name}_v${speed}.log" | grep -E "^(gps|drift|lost)|refused" | sed 's/^/    /'
  sleep 5                                                    # the camera's USB stream restarts
}

IFS=, read -ra SP <<< "$SPEEDS"
IFS=, read -ra AM <<< "$AMOUNTS"
IFS=, read -ra KI <<< "$KINDS"
for v in "${SP[@]}"; do run clear "$v" none 0; done
for k in "${KI[@]}"; do
  for a in "${AM[@]}"; do
    for v in "${SP[@]}"; do run "${k}_a${a}" "$v" "$k" "$a"; done
  done
done
for v in "${SP[@]}"; do run worst "$v" heavyrain,wind,fog,birds,drones,insects 0.5; done
echo "=== done: python3 navera_tools/bench/summarise_day_real.py $OUT"
