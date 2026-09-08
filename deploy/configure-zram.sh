#!/usr/bin/env bash
# Configure optional compressed swap when no zram device is active.
set -u

SIZE="${RAZAAI_ZRAM_SIZE:-2G}"

if ! modprobe zram 2>/dev/null; then
  echo "[zram] kernel module unavailable; skipping"
  exit 0
fi

if swapon --noheadings 2>/dev/null | awk '{print $1}' | grep -q '/dev/zram'; then
  echo "[zram] already active"
  exit 0
fi

if [ ! -e /sys/block/zram0 ]; then
  echo "[zram] /sys/block/zram0 missing; skipping"
  exit 0
fi

# Prefer zstd, fall back to the kernel default.
echo zstd > /sys/block/zram0/comp_algorithm 2>/dev/null || true

# disksize takes bytes; accept K/M/G suffixes.
case "$SIZE" in
  *G) BYTES=$(( ${SIZE%G} * 1024 * 1024 * 1024 ));;
  *M) BYTES=$(( ${SIZE%M} * 1024 * 1024 ));;
  *K) BYTES=$(( ${SIZE%K} * 1024 ));;
  *)  BYTES=$(( SIZE ));;
esac

if ! echo "$BYTES" > /sys/block/zram0/disksize 2>/dev/null; then
  echo "[zram] could not set disksize; skipping"
  exit 0
fi

mkswap /dev/zram0 >/dev/null && swapon -p 100 /dev/zram0
echo "[zram] active: /dev/zram0 $SIZE, priority 100"
