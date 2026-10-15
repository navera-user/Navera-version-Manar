#!/bin/bash
# The solution flies everything a student flies (the check grades the files the runs write). ≈ 2–3 min.
set -e
python3 campaign.py run > /dev/null
python3 -m navera_lite.sim.run campaign/plane_delayed.json --quiet > /dev/null
python3 campaign.py report > /dev/null
python3 campaign.py run --mine > /dev/null
python3 campaign.py report --mine > /dev/null
cp navera_lite/spoof.py my_spoof.py && sed -i 's/"confirm_n": 2,/"confirm_n": 6,/' my_spoof.py
python3 campaign.py run --mine --part spoof=my_spoof.py > /dev/null
python3 campaign.py report --mine > /dev/null
python3 vision_check.py > /dev/null
python3 -m navera_lite.sim.run campaign/night_mine.json --mine --quiet > /dev/null
python3 -m navera_lite.sim.run my_scenario.json --quiet > /dev/null
