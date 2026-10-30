#!/bin/bash
# Teacher only (tools/try_lesson.py --solution): the whole project of the example solution (idea 1, "a held fix
# states a sigma that grows with its age"), done as a student does it, step by step. ≈ 1 min 30.
set -e
source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true      # as in the student's terminal (~/.bashrc)
sol="$HOME/.sol33"
rm -rf "$sol" && mkdir -p "$sol"
mv _project/* "$sol"/ && rmdir _project
mv _apply.sh "$sol"/                     # not part of the student's repository (bash keeps reading it)
bash navera_lite/tools/init_repo.sh >/dev/null                         # Step 1
git switch -q -c project/ageing-sigma                                  # Step 2
cp "$sol/project.json" project.json                                    # Step 3
cp "$sol/test_ageing.py" navera_lite/tests/test_ageing.py              # Step 4
cp "$sol/answers.py" answers.py
git add project.json navera_lite/tests/test_ageing.py
git commit -q -m "test: a held fix must state a sigma that grows with its age (red)"
python3 project.py red >/dev/null
git tag before                                                         # Step 5
python3 project.py campaign before >/dev/null
git apply "$sol/change.patch"                                          # Step 6
git add navera_lite navera_lite.yaml
git commit -q -m "judge: a held fix states sigma = sqrt(sigma^2 + (age_speed x age)^2), age_speed 15 m/s"
python3 project.py green >/dev/null
python3 project.py campaign after >/dev/null                           # Step 7
python3 project.py evaluate >/dev/null 2>&1                            # Step 8
sed -e "s/{CHANGE_SHA}/$(git rev-parse --short HEAD)/" \
    -e "s/{BEFORE_DATE}/$(git log -1 --format=%ad --date=short before)/" "$sol/REPORT.md" > REPORT.md   # Step 9
git diff before HEAD -- navera_lite navera_lite.yaml > my_project.patch                          # Step 10
git apply --check -R my_project.patch
git add REPORT.md answers.py
git commit -q -m "docs: project report"
