#!/bin/bash
# The git steps of lab 5, as a student types them (run from ~/lessons/05-git).
set -e
git config --global user.name "Test Student"
git config --global user.email "test.student@example.com"
cd ~/navera
git status
git switch -c my-first-change
printf '\n- Test Student was here: my first commit!\n' >> ACADEMY_README.md
git diff
git add ACADEMY_README.md
git commit -m "Add my name to the academy README"
sed -i 's/info("Read thread started")/info("Read thread started, listening to the GPS receiver")/' gps_pkg/gps_pkg/nodes/gps_node.py
git diff --stat
git add gps_pkg/gps_pkg/nodes/gps_node.py
git commit -m "gps_node: clearer start-up log message"
git log --oneline
rm navera_common/navera_common/geo.py
git status --short
git restore navera_common/navera_common/geo.py
git status
FIRST=$(git rev-list --reverse base..my-first-change | head -n 1 | cut -c1-7)
cd ~/lessons/05-git
sed -i "s/^FIRST_COMMIT = \"\"/FIRST_COMMIT = \"$FIRST\"/" answers.py
