#!/bin/bash
# The lab's change in the NAVERA copy: a FIX now needs a stated sigma of at most 2 m.
set -e
sed -i 's/^\(\s*fix_max_sigma_m:\s*\)25\.0/\12.0/' ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
grep -n "fix_max_sigma_m:" ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
