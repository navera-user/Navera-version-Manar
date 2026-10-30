#!/usr/bin/env bash
#
# setup_fs.sh — filesystem settings for a box whose power can be cut at any moment (the drone
# battery unplugged): the boot must succeed afterwards, whatever was being written.
#
#   deploy/setup_fs.sh --check              # report only (no root): exit 1 when a FAIL is found
#   sudo deploy/setup_fs.sh                 # apply: fsck.repair=yes on the kernel command line
#   sudo deploy/setup_fs.sh --dry-run       # print what would be done
#   deploy/setup_fs.sh --root /tmp/stage    # staged (no root): the files under DIR
#
# What is checked / done:
#   root ext4 mount options  data=ordered (the ext4 default) and barriers ON; FAIL on
#                            data=writeback, nobarrier or barrier=0 (a cut then leaves
#                            files with garbage). commit= (default 5 s: at most 5 s of
#                            writes lost) is reported, never changed.
#   fsck at boot             the root line of /etc/fstab has fsck pass 1 (Jetson default),
#                            /data (if listed) pass 2 and nofail (a broken data disk never
#                            blocks the boot).
#   fsck.repair=yes          added to the APPEND line of /boot/extlinux/extlinux.conf (a copy
#                            .navera-bak is kept): systemd-fsck then repairs the root file
#                            system on its own instead of stopping the boot at a prompt that
#                            nobody sees on a sealed box. Applied by install.sh --product.
#   journald                 Storage=persistent: journal files are append-only and a file
#                            cut by the power is set aside by journald at the next start
#                            (never blocks the boot); deploy/journald/navera.conf.
# Not done here (documented option, deploy/README.md §13.2): a read-only root (overlayroot).
# NAVERA's own writes are atomic (navera_common/atomic_io.py) and its readers tolerant.
set -euo pipefail

DRY=0; CHECK=0; R="${DESTDIR:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --check) CHECK=1 ;;
    --root) shift; R="$1" ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$R" ] && R="$(realpath -m "$R")"
FSTAB="$R/etc/fstab"
EXTLINUX="${NAVERA_EXTLINUX:-$R/boot/extlinux/extlinux.conf}"
fails=0
say() { echo "  $1  $2"; [ "$1" = FAIL ] && fails=$((fails + 1)); return 0; }
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else "$@"; fi; }

# root mount options: the live ones (real box) or the fstab line (staged)
if [ -z "$R" ]; then
  opts=$(findmnt -no OPTIONS / 2>/dev/null || true)
else
  opts=$(awk '$2 == "/" {print $4}' "$FSTAB" 2>/dev/null || true)
fi
case ",$opts," in
  *,data=writeback,*|*,nobarrier,*|*,barrier=0,*) say FAIL "root mounted with $opts: use the ext4 defaults (data=ordered, barriers)" ;;
  *) say PASS "root mount options '${opts:-defaults}' (data=ordered, barriers on; commit $(echo ",$opts," | grep -o 'commit=[0-9]*' || echo 'default 5 s'))" ;;
esac

if [ -f "$FSTAB" ]; then
  pass=$(awk '$2 == "/" {print $6}' "$FSTAB")
  [ "${pass:-0}" = 1 ] && say PASS "fsck of the root file system at boot (fstab pass 1)" \
                       || say WARN "root line of $FSTAB has fsck pass '${pass:-none}' (1 expected)"
  data=$(awk '$2 == "/data"' "$FSTAB")
  if [ -n "$data" ]; then
    echo "$data" | grep -q nofail && say PASS "/data has nofail (a broken data disk does not block the boot)" \
                                  || say FAIL "/data in $FSTAB without nofail: a broken disk would stop the boot"
  fi
else
  say WARN "$FSTAB not found"
fi

if [ -f "$EXTLINUX" ] && ! grep -qE '^\s*APPEND' "$EXTLINUX"; then
  say WARN "$EXTLINUX has no APPEND line: add fsck.repair=yes to the kernel command line by hand"
elif [ -f "$EXTLINUX" ]; then
  if grep -E '^\s*APPEND' "$EXTLINUX" | grep -qv 'fsck.repair=yes'; then
    if [ "$CHECK" = 1 ]; then
      say WARN "fsck.repair=yes not on the kernel command line ($EXTLINUX): sudo deploy/setup_fs.sh"
    else
      n_before=$(grep -cE '^\s*APPEND' "$EXTLINUX")
      run cp -p "$EXTLINUX" "$EXTLINUX.navera-bak"
      if [ "$DRY" = 0 ]; then
        tmp="$EXTLINUX.navera-tmp"
        sed -E '/^\s*APPEND/{/fsck\.repair=yes/!s/$/ fsck.repair=yes/}' "$EXTLINUX" > "$tmp"
        # the edit only appends to the APPEND lines: anything else = refuse (an unbootable box)
        if [ "$(grep -E '^\s*APPEND' "$tmp" | grep -c 'fsck\.repair=yes')" = "$n_before" ] \
           && [ "$(wc -l < "$tmp")" = "$(wc -l < "$EXTLINUX")" ]; then
          # only this file and its file system: a bare `sync` waits for every disk on the box
          # (a USB disk being filled kept it, and this step, blocked for minutes)
          sync "$tmp"; mv -f "$tmp" "$EXTLINUX"; sync -f "$EXTLINUX"
          say PASS "fsck.repair=yes added to $EXTLINUX (copy: $EXTLINUX.navera-bak)"
        else
          rm -f "$tmp"; say FAIL "could not add fsck.repair=yes safely to $EXTLINUX: left unchanged"
        fi
      fi
    fi
  else
    say PASS "fsck.repair=yes on the kernel command line"
  fi
else
  say WARN "$EXTLINUX not found (not a Jetson L4T boot): add fsck.repair=yes to the kernel command line by hand"
fi

jd="$R/etc/systemd/journald.conf.d/navera.conf"
if [ -f "$jd" ] && grep -q '^Storage=persistent' "$jd"; then
  say PASS "journald: persistent, size-capped ($jd)"
else
  say WARN "journald drop-in $jd absent: deploy/install.sh installs it"
fi
[ "$fails" = 0 ] || exit 1
exit 0
