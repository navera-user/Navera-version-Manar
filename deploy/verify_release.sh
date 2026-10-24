#!/usr/bin/env bash
#
# verify_release.sh — check a NAVERA release archive BEFORE extracting it (no root).
#
#   verify_release.sh navera-VERSION.tar.gz [IRIS_PUBLIC_KEY]
#
#   1. navera-VERSION.tar.gz.sha256 next to it matches (a damaged copy / download)
#   2. a signature next to it is valid: .sig with an openssl public key (PEM, given as the
#      second argument), or .asc with gpg (the IRIS key imported in gpg, or given as a
#      .asc / .gpg key file as the second argument)
#   NAVERA_RELEASE_REQUIRE_SIG=1  a missing signature is a failure (delivered boxes)
# Exit 0 = the archive can be installed. This script is also delivered beside the archive
# (it cannot be taken from inside an archive not yet verified).
set -euo pipefail
a=${1:?usage: verify_release.sh navera-VERSION.tar.gz [IRIS_PUBLIC_KEY]}
key=${2:-}
[ -f "$a" ] || { echo "no archive $a" >&2; exit 2; }
if [ -f "$a.sha256" ]; then
  (cd "$(dirname "$a")" && sha256sum -c --quiet "$(basename "$a").sha256") || { echo "FAIL  sha256 of $a" >&2; exit 1; }
  echo "PASS  sha256"
else
  echo "WARN  no $a.sha256"
fi
if [ -f "$a.sig" ]; then
  [ -n "$key" ] || { echo "FAIL  $a.sig needs the IRIS public key (PEM) as second argument" >&2; exit 1; }
  openssl dgst -sha256 -verify "$key" -signature "$a.sig" "$a" >/dev/null 2>&1 \
    || { echo "FAIL  signature $a.sig does NOT match $key: do not install" >&2; exit 1; }
  echo "PASS  signature (openssl, $(basename "$key"))"
elif [ -f "$a.asc" ]; then
  if [ -n "$key" ]; then
    kr=$(mktemp -d); trap 'rm -rf "$kr"' EXIT
    gpg --batch --quiet --homedir "$kr" --import "$key" 2>/dev/null
    gpg --batch --homedir "$kr" --verify "$a.asc" "$a" 2>/dev/null \
      || { echo "FAIL  gpg signature $a.asc does NOT match $key: do not install" >&2; exit 1; }
  else
    gpg --batch --verify "$a.asc" "$a" 2>/dev/null || { echo "FAIL  gpg signature $a.asc" >&2; exit 1; }
  fi
  echo "PASS  signature (gpg)"
elif [ "${NAVERA_RELEASE_REQUIRE_SIG:-0}" = 1 ]; then
  echo "FAIL  no signature ($a.sig / $a.asc) and NAVERA_RELEASE_REQUIRE_SIG=1" >&2; exit 1
else
  echo "WARN  unsigned release"
fi
echo "release OK: tar xzf $(basename "$a")"
