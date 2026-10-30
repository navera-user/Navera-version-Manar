#!/usr/bin/env bash
# make_release.sh VERSION [OUTDIR] — the Academy release tarball from the COMMITTED tree (git archive):
# no .git, no state/ students/ logs/ base/ (git-ignored), no internal reviews or dev-only setup scripts,
# segno vendored for the QR codes (setup/vendor). Writes OUTDIR/navera-academy-VERSION.tar.gz + .sha256.
set -euo pipefail
V="${1:?version}"; OUT="${2:-$HOME/navera_releases}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "commit first (tracked files changed)" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
D="$TMP/navera-academy-$V"; mkdir -p "$D"
git archive --format=tar HEAD | tar x -C "$D"
rm -rf "$D/reviews" "$D/setup/install.sh" "$D/setup/uninstall.sh" "$D/setup/netkeeper.py" "$D/tools/set_oauth.py"
SEGNO="${SEGNO_DIR:-}"
[ -n "$SEGNO" ] || SEGNO="$ROOT/setup/vendor"
[ -d "$SEGNO/segno" ] || { echo "segno missing (SEGNO_DIR=DIR holding segno/): certificate QR codes need it" >&2; exit 1; }
mkdir -p "$D/setup/vendor"; cp -a "$SEGNO/segno" "$D/setup/vendor/"
[ -f "$D/setup/vendor/segno/__init__.py" ] || { echo "setup/vendor/segno not in the release" >&2; exit 1; }
echo "$V $(git rev-parse --short HEAD) $(date +%F)" > "$D/VERSION"
# never ship a secret or dev data
if grep -rIl -E "BEGIN [A-Z ]*PRIVATE KEY|client_secre[t]|tskey-[a-z]" "$D" | grep -v '/vendor/' ; then echo "secret-looking file above: refused" >&2; exit 1; fi
for x in state students logs base .git; do [ ! -e "$D/$x" ] || { echo "$x in the release: refused" >&2; exit 1; }; done
find "$D" -name '__pycache__' -prune -exec rm -rf {} +
mkdir -p "$OUT"
tar czf "$OUT/navera-academy-$V.tar.gz" --owner=0 --group=0 --numeric-owner -C "$TMP" "navera-academy-$V"
(cd "$OUT" && sha256sum "navera-academy-$V.tar.gz" > "navera-academy-$V.tar.gz.sha256")
cp "$ROOT/deploy/install_academy.sh" "$OUT/install_academy.sh"
ls -la "$OUT/navera-academy-$V.tar.gz"*; cat "$OUT/navera-academy-$V.tar.gz.sha256"
