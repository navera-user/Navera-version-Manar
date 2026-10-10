# Lab 30 report — detecting GPS spoofing

Name:

<!-- Write in your own words, short sentences. Quote your numbers (with units).
     Replace every TODO. Keep the five "## " headings: the check reads them. -->

## 1. The patient spoofer

<!-- Use patient_accept_time() and results.json "patient": after how many seconds does the 2 km
     spoof become "reachable"? At which t did your guard accept it? Why do the two differ a little?
     What happens to the TRUE GPS at t = 120 s, and why is that worse than the spoof itself? -->
TODO

## 2. Choosing an operating point

<!-- Give your rule (k = ..., n = ...), its P_FA and P_D from results.json, and its mean delay.
     Why is it not NAVERA's point (k = 3, n = 5)? Hint: an honest flight of 1 hour has 1800 vision
     checks, not 60 — what happens to P_FA? And what does a false alarm cost (a good GPS refused)? -->
TODO

## 3. Correlated vision errors

<!-- Compare P_FA with independent errors and with rho = 0.9 (results.json "correlated").
     Why does correlation break the p^n formula? What does it mean for a real map-matching camera? -->
TODO

## 4. The real arbiter

<!-- From real_drift.txt: the GPS offset when the real arbiter said IN DOUBT and when it refused
     the GPS. Compare with your guard (python3 spoof.py, attack "drift"). Why can they not be
     identical (drift speed, vision rate, the max_speed x time-gap term)? -->
TODO

## 5. Limits

<!-- At least three limits of NAVERA's protection, each with the reason (unknown vision sigma,
     sea / desert with no landmark, a spoofer who stays under 3 sigma, correlated errors...).
     Then ONE extra protection you would add and what it would need (hardware, data, test). -->
TODO
