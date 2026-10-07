#!/bin/bash
# The git steps of lab 5, as a student types them (run from ~/lessons/05-git).
set -e
git config --global user.name "Test Student"
git config --global user.email "test.student@example.com"
cd ~/navera
git status
git log --oneline --graph --all --decorate
git switch -c my-first-change
printf '\n- Test Student was here: my first commit in NAVERA!\n' >> ACADEMY_README.md
git add ACADEMY_README.md
git commit -m "docs(academy): add my name to the academy README"
sed -i 's/info("Read thread started")/info("Read thread started, listening to the GPS receiver")/' gps_pkg/gps_pkg/nodes/gps_node.py
python3 -m py_compile gps_pkg/gps_pkg/nodes/gps_node.py
git add gps_pkg/gps_pkg/nodes/gps_node.py
git commit -m "fix(gps): clearer start-up log message"
git format-patch base --stdout > ~/lessons/05-git/my_changes.patch
git apply --stat ~/lessons/05-git/review_me.patch
git apply --check ~/lessons/05-git/review_me.patch
git apply --exclude=navera_estimator/navera_estimator/config/estimator_params.yaml ~/lessons/05-git/review_me.patch
python3 -m py_compile navera_common/navera_common/geo.py
git add navera_common/navera_common/geo.py
git commit -m "refactor(geo): use EARTH_RADIUS_M in haversine_m"
git tag -a lab5 -m "Lab 5: two changes and a reviewed patch"
rm navera_common/navera_common/geo.py
git restore navera_common/navera_common/geo.py
git status
FIRST=$(git rev-list --reverse base..my-first-change | head -n 1 | cut -c1-7)
cd ~/lessons/05-git
sed -i "s/^FIRST_COMMIT = \"\"/FIRST_COMMIT = \"$FIRST\"/" answers.py
