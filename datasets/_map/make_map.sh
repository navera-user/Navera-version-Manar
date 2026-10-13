#!/usr/bin/env bash
# Rebuild the NAVERA Academy OSM map of Sousse end to end (see README.md).
#   ./make_map.sh                 all steps
#   ./make_map.sh render verify   only some steps
# Tools live in a private pip --target dir (never the shared user site; numpy stays the system 1.x).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PYLIB="${OSM_PYLIB:-$HOME/osmrender/pylib}"
if [ ! -d "$PYLIB/mapnik" ]; then
  echo "installing mapnik/osmium/shapely into $PYLIB (private, --no-deps)"
  pip install --no-deps --target "$PYLIB" mapnik==4.3.2 osmium==4.3.1 shapely==2.1.2
fi
export PYTHONPATH="$PYLIB${PYTHONPATH:+:$PYTHONPATH}"
export PROJ_DATA="$PYLIB/mapnik/share/proj"
exec python3 "$HERE/make_map.py" "$@"
