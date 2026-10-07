# Lab 5 — answers. Save with Ctrl+S when you are done.

# 1. The short hash of YOUR FIRST commit on the branch my-first-change.
#    git -C ~/navera log --oneline --decorate
#    It is the FIRST word of the line that shows YOUR first message (the README one).
#    Not a hash from the "NAVERA base — …" line.
FIRST_COMMIT = ""

# 2. The base commit's line looks like:   b0e06dc NAVERA base — fa775cd fix(bench): …
#    Its message contains a SECOND hash: the commit of the real NAVERA repository the
#    academy copied. Write that second hash (7 characters) here.
NAVERA_SOURCE_COMMIT = ""

# For the questions below, write ONE letter between the quotes, e.g.  Q1 = "b"

# Q1. What does `git add file` do?
#   a) it saves the file in the history for ever
#   b) it puts the current change of this file in the staging area: it will be in the NEXT commit
#   c) it sends the file to the academy server
Q1 = ""

# Q2. What does `git diff base...my-first-change` (three dots) show?
#   a) everything that differs between base and the files in your folder now
#   b) the changes made on base since your branch started
#   c) the changes made on my-first-change since it left base
Q2 = ""

# Q3. You press "Reset my NAVERA copy" in the dashboard. What happens to your commits?
#   a) they are lost for ever
#   b) they are saved in a git bundle in your backup folder, then ~/navera becomes a fresh clone of the base
#   c) they are sent to the real NAVERA product
Q3 = ""

# Q4. git status says: "Your branch is up to date with 'base/work'". It means:
#   a) work points at the same commit as base/work, the remote's branch as recorded at the clone;
#      nothing was sent or received
#   b) your commits were uploaded to the academy server
#   c) the real NAVERA repository has no new commits
Q4 = ""

# Q5. You merge my-first-change into a branch that has no commit of its own since they split. Git:
#   a) always creates a merge commit with two parents
#   b) refuses: branches can never be merged back
#   c) can fast-forward: the branch label simply moves to the last commit, no new commit
Q5 = ""

# Q6. Annotated tag vs lightweight tag:
#   a) they are exactly the same
#   b) an annotated tag is an object with its own author, date and message; a lightweight tag is just a name
#   c) an annotated tag moves forward with every new commit
Q6 = ""
