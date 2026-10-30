# Memo — what NAVERA Lite's GNSS part refuses, and what it cannot see

<!-- Write 150–350 words in your own words, for an engineer of the NAVERA team. Keep the three headings
     exactly as they are. Quote your numbers from `run_gnss.py log`, `forge`, `dop` and `drive` (results.json).
     Delete these comment lines if you want. -->

## What the wire did to the drive

<!-- How many lines did is_valid refuse, and what had happened to them? Which damaged line passed the
     checksum, and what stopped it? Your forged line: how far did one swap move the fix? -->

## What the sky did to σ

<!-- Where was the geometry worst (largest HDOP, satellites used), and what σ and state did your stack give
     there? How many seconds FIX, DEGRADED and NO_FIX, and why NO_FIX? -->

## What gnss.py cannot see

<!-- The jump your gnss part accepted: when, how far, with what σ? Which part of a navigation stack refuses
     it, and what would still get through that part too? -->
