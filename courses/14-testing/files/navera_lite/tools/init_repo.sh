#!/usr/bin/env bash
# navera_lite/tools/init_repo.sh — make your lesson folder a git repository, with one first commit tagged
# "start". Part of NAVERA Lite, the course's teaching stack (mission 14; mission 33 uses it again).
# Written for the course; it is not NAVERA code.
#
#     bash navera_lite/tools/init_repo.sh        (from the lesson folder)
#
# After it, `git diff start` shows everything you changed since, and `git restore <file>` throws an edit
# away (mission 05). Running it twice changes nothing.
set -e
cd "$(dirname "$0")/../.."                      # the lesson folder: the one that holds navera_lite/
here="$(pwd)"
if [ -d .git ]; then
    echo "$here is already a git repository:"
    git log --oneline -1 start 2>/dev/null || git log --oneline -1
    exit 0
fi
git init -q -b main
# your name from mission 05 (git config --global) is used if you set it; otherwise a local one
git config user.name  >/dev/null || git config user.name  "student"
git config user.email >/dev/null || git config user.email "student@academy.local"
cat > .gitignore <<'IGNORE'
__pycache__/
.pytest_cache/
.hypothesis/
*.log
IGNORE
git add -A
git commit -q -m "start: $(basename "$here") as given"
git tag start
echo "git repository created in $here"
git log --oneline -1
echo "$(git ls-files | wc -l) files committed, tagged 'start'"
