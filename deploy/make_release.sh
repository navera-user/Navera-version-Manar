#!/usr/bin/env bash
#
# make_release.sh — build a NAVERA release archive from a committed git revision.
#
#   deploy/make_release.sh VERSION [REV=HEAD] [OUT_DIR=~/navera_releases]
#
# The archive is `git archive` of REV: committed files only (no .git, no worktrees, no
# build products, no local changes), so a box installed from it runs exactly that revision.
# It adds:
#   VERSION                      the version, the revision and its date
#   RELEASE_MANIFEST.sha256      a sha256 of every file in the release
# and writes, next to the archive, navera-VERSION.tar.gz.sha256.
# The tree must be clean (no uncommitted change to tracked files) and REV must exist.
# Before releasing: all tests (navera_tools/run_tests.sh), python3 navera_tools/trace_matrix.py
# --check, deploy/stage_check.sh. On the box:
#   tar xzf navera-VERSION.tar.gz && cd navera-VERSION && sha256sum -c RELEASE_MANIFEST.sha256 --quiet
#   sudo deploy/install.sh
set -euo pipefail

version=${1:?usage: deploy/make_release.sh VERSION [REV] [OUT_DIR]}
rev=${2:-HEAD}
out=${3:-$HOME/navera_releases}
repo=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.]+)?$ ]] || { echo "VERSION must look like 0.5.0" >&2; exit 2; }
git -C "$repo" rev-parse --verify -q "$rev^{commit}" >/dev/null || { echo "no revision $rev" >&2; exit 2; }
if [ "$rev" = HEAD ] && ! git -C "$repo" diff --quiet HEAD --; then
    echo "uncommitted changes to tracked files: commit them or name a revision" >&2
    exit 2
fi

name="navera-$version"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$repo" archive --format=tar --prefix="$name/" "$rev" | tar -x -C "$tmp"

sha=$(git -C "$repo" rev-parse "$rev")
date=$(git -C "$repo" show -s --format=%cs "$rev")
printf '%s\nrevision %s\ndate %s\n' "$version" "$sha" "$date" > "$tmp/$name/VERSION"
(cd "$tmp/$name" && find . -type f ! -name RELEASE_MANIFEST.sha256 -print0 | sort -z \
    | xargs -0 sha256sum > RELEASE_MANIFEST.sha256)

mkdir -p "$out"
tar -C "$tmp" -czf "$out/$name.tar.gz" "$name"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")
files=$(wc -l < "$tmp/$name/RELEASE_MANIFEST.sha256")
echo "$out/$name.tar.gz ($files files, revision ${sha:0:7}, $date)"
