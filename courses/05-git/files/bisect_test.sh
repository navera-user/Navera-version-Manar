#!/bin/bash
# bisect_test.sh — is the commit checked out NOW good or bad? (lab Step 7, TODO 4)
#
# `git bisect run` calls this script once per commit it tests, in the top folder of the repository.
# Its EXIT CODE is the answer (lesson §4):
#     0    good: the jump gate behaves as in lesson 1
#     1    bad: it does not
#     125  this commit cannot be tested (its code does not even import): skip it
#
# The test: ~/lessons/05-git/probe_gate.py prints how many of lesson 1's 8 fixes (the trusted one,
# then the table's 7 rows) the gate refuses (the right number is 5). When this commit's code cannot
# be imported, the probe prints nothing on stdout and exits with code 3.
#
# Try it by hand, from inside navera-lite-history:   bash ../bisect_test.sh; echo "exit code: $?"

# TODO 4 ------------------------------------------------------------------------------------------
echo "bisect_test.sh is not written yet (TODO 4)" >&2
exit 255
