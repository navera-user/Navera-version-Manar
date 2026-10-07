# Lab 5 — answers. Save with Ctrl+S when you are done.

# 1. The short name (hash) of your FIRST commit on the branch my-first-change.
#    Find it with:   git -C ~/navera log --oneline
#    (the 7 letters/digits at the start of the line; copy them between the quotes)
FIRST_COMMIT = ""

# For the questions below, write the letter of your answer between the quotes, e.g.  Q1 = "b"

# Q1. What does `git add file` do?
#   a) it saves the file in the history for ever
#   b) it puts the change of this file in the staging area: it will be in the NEXT commit
#   c) it sends the file to the internet
Q1 = "b"

# Q2. You deleted a file of ~/navera by mistake with rm, and you have not committed since.
#     Which command brings it back?
#   a) git restore <file>      b) git commit -m "back"      c) git branch <file>
Q2 = "a"

# Q3. You press "Reset my NAVERA copy" in the dashboard. What happens to your commits?
#   a) they are lost for ever
#   b) they are saved in a backup (a git bundle), then ~/navera becomes a fresh copy of the base
#   c) they are sent to the real NAVERA product
Q3 = "b"
