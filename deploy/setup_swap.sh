#!/usr/bin/env bash
#
# setup_swap.sh — give the Jetson a swap file on disk, kept across reboots (F5 / H-11).
#
#   sudo deploy/setup_swap.sh                 # make / activate /swapfile if disk swap is short
#   deploy/setup_swap.sh --check              # only say whether disk swap is enough (no root)
#   sudo deploy/setup_swap.sh --dry-run       # print what would be done
#   deploy/setup_swap.sh --root /tmp/stage    # staged (no root): the file and the fstab line
#                                             # under DIR; swapon is skipped and listed
#
# Why: on the 8 GB Orin Nano the day pipeline peaked at 3.5 GB and was OOM-killed after 4.6 min
# without swap (F5); with a 16 GB swap file the same run completed. JetPack's zram swap lives
# in RAM: it does not count here. Only swap on disk counts.
#
# Settings (environment, or /etc/navera/navera.env through install.sh):
#   NAVERA_SWAP_MB      size of the swap file to make            (default 8192)
#   NAVERA_MIN_SWAP_MB  disk swap below this = not enough         (default 4096)
#   NAVERA_SWAP_FILE    path of the swap file                     (default /swapfile)
# Never shrinks or replaces an active swap; refuses when the disk would keep less than 2 GB free.
# Exit 0 = enough disk swap (or made now), 1 = not enough (--check) or failed.
set -euo pipefail

SIZE_MB="${NAVERA_SWAP_MB:-8192}"
MIN_MB="${NAVERA_MIN_SWAP_MB:-4096}"
FILE="${NAVERA_SWAP_FILE:-/swapfile}"
SWAPS="${NAVERA_SWAPS:-/proc/swaps}"        # tests point these at fixtures
KEEP_FREE_MB=2048
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
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else "$@"; fi; }

# disk swap in MB: /proc/swaps entries that are not zram (sizes are in KiB)
disk_swap_mb() { awk 'NR > 1 && $1 !~ /^\/dev\/zram/ { kb += $3 } END { print int(kb / 1024) }' "$SWAPS" 2>/dev/null || echo 0; }

have=$(disk_swap_mb)
if [ "$have" -ge "$MIN_MB" ]; then
  echo "swap: ${have} MB on disk active (>= ${MIN_MB} MB): OK"
  [ -z "$R" ] && exit 0
fi
if [ "$CHECK" = 1 ]; then
  echo "swap: WARNING only ${have} MB on disk (need >= ${MIN_MB} MB; zram does not count): sudo $0" >&2
  exit 1
fi
[ "$DRY" = 0 ] && [ -z "$R" ] && [ "$(id -u)" != 0 ] && { echo "run it with sudo: sudo $0" >&2; exit 1; }

target="$R$FILE"
# a swap area made by mkswap ends its first 4 KiB page with this signature
is_swap() { [ -f "$1" ] && [ "$(head -c 4096 "$1" 2>/dev/null | tail -c 10)" = SWAPSPACE2 ]; }
if is_swap "$target" && [ "$(stat -c %s "$target")" -ge $(( SIZE_MB * 1024 * 1024 )) ]; then
  echo "swap: $target exists ($(( $(stat -c %s "$target") / 1048576 )) MB): kept"
else
  [ -e "$target" ] && { echo "swap: $target exists but is not a swap area of ${SIZE_MB} MB: not touched (remove it or set NAVERA_SWAP_FILE)" >&2; exit 1; }
  d=$(dirname "$target"); while [ ! -d "$d" ]; do d=$(dirname "$d"); done   # nearest existing folder
  free_mb=$(df -Pm "$d" | awk 'NR == 2 { print $4 }')
  if [ "$free_mb" -lt $(( SIZE_MB + KEEP_FREE_MB )) ]; then
    echo "swap: not enough disk for ${SIZE_MB} MB (${free_mb} MB free, ${KEEP_FREE_MB} MB kept free): set a smaller NAVERA_SWAP_MB" >&2
    exit 1
  fi
  echo "swap: making $target (${SIZE_MB} MB)"
  # made under a temporary name and renamed when complete: an interrupted run leaves no half file
  part="$target.part"
  run mkdir -p "$(dirname "$target")"
  run rm -f "$part"
  # fallocate is instant; some filesystems refuse it for swap: dd then
  run fallocate -l "${SIZE_MB}M" "$part" || run dd if=/dev/zero of="$part" bs=1M count="$SIZE_MB" status=none
  run chmod 600 "$part"
  run mkswap "$part"
  run mv "$part" "$target"
fi

fstab="$R/etc/fstab"
if [ -f "$fstab" ] && awk -v f="$FILE" '$1 == f && $3 == "swap"' "$fstab" | grep -q .; then
  echo "swap: $FILE already in $fstab"
else
  echo "swap: adding $FILE to $fstab (active at every boot)"
  if [ "$DRY" = 1 ]; then echo "  + echo '$FILE none swap sw 0 0' >> $fstab"
  else mkdir -p "$(dirname "$fstab")"; echo "$FILE none swap sw 0 0" >> "$fstab"; fi
fi

if [ -n "$R" ]; then
  echo "  (staged in $R: skipped) swapon $FILE"
  exit 0
fi
if ! awk -v f="$FILE" 'NR > 1 && $1 == f' "$SWAPS" | grep -q .; then
  run swapon "$FILE"
fi
[ "$DRY" = 1 ] && exit 0
echo "swap: $(disk_swap_mb) MB on disk active"
[ "$(disk_swap_mb)" -ge "$MIN_MB" ]
