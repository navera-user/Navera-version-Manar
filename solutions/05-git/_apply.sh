#!/bin/bash
# The git steps of lab 5, as a student types them (run from ~/lessons/05-git by tools/try_lesson.py).
set -e
git config --global user.name "Test Student"
git config --global user.email "test.student@example.com"
tar -xzf /data/academy/05-git/navera-lite-history.tar.gz
cd navera-lite-history
git log --oneline --graph --all --decorate | head -n 5
git switch -c my-first-change
git diff main...kenji/fewer-refusals > ../review_me.patch
git apply --check ../review_me.patch
git apply --include=README.md --include=navera_lite/geo.py ../review_me.patch
python3 -m pytest -q tests
git add README.md
git commit -q -m "docs(readme): fix the spelling of receive"
git add navera_lite/geo.py
git commit -q -m "refactor(geo): haversine_m uses EARTH_RADIUS_M"
python3 ../probe_gate.py
cp ../test_regression.py tests/
python3 -m pytest -q tests || true
git add tests/test_regression.py
git commit -q -m "test(guard): the gate widens again after a jump"
git bisect start main v0.1
git bisect run ../bisect_test.sh
git bisect log > ../bisect.log
git bisect reset
BAD=$(sed -n 's/^# first bad commit: \[\([0-9a-f]*\)\].*/\1/p' ../bisect.log)
git revert --no-edit "$BAD"
python3 -m pytest -q tests
rm navera_lite/guard.py
git restore navera_lite/guard.py
git reset --hard HEAD~2
git reflog -4
git reset --hard "HEAD@{1}"
git format-patch main --stdout > ../my_changes.patch
git status
