"""detective.py — YOUR code for lab 5: read a patch like git does, and find a bad commit like git bisect.

    TODO 1  hunk_header   the four numbers of a hunk header "@@ -a,b +c,d @@"   (lesson §3)
    TODO 2  diff_stat     added / removed lines per file of a patch              (lesson §3)
    TODO 3  first_bad     binary search for the first bad commit                 (lesson §4)

Run `python3 run_lab.py test` to try each function on its example.
"""

# A small patch (the worked example of lesson §3), exactly as `git diff` writes it: two files, one hunk each.
# Careful: an empty context line is written as ONE SPACE.
EXAMPLE_PATCH = """diff --git a/README.md b/README.md
index 390b40b..743368c 100644
--- a/README.md
+++ b/README.md
@@ -11,6 +11,8 @@ the last trusted fix than the vehicle can fly in the elapsed time, plus a margin
 
 ## Settings
 
+Ask Priya before you change a value.
+
 The gate's values are in `navera_lite.yaml` (ROS 2 params-file format). Change them only with a
 measurement that shows why.
 
diff --git a/navera_lite.yaml b/navera_lite.yaml
index 0753941..dfb8f24 100644
--- a/navera_lite.yaml
+++ b/navera_lite.yaml
@@ -3,4 +3,4 @@
   ros__parameters:
     max_speed_mps: 100.0        # v_max of the jump gate (m/s)
     gps_jump_margin_m: 50.0     # margin of the jump gate (m)
-    gps_timeout_s: 3.0          # a GPS fix older than this is not fresh (s)
+    gps_timeout_s: 10.0         # GPS drops out a lot over the hills
"""


# TODO 1 ------------------------------------------------------------------------------------
def hunk_header(line):
    """The four numbers of a hunk header of a unified diff (lesson §3).

    line: one line that starts with "@@", e.g. "@@ -12,7 +12,9 @@ def check(self, t_s, xy):"
    Returns (old_start, old_count, new_start, new_count), four ints. A count that is left out means 1.

    Examples:  hunk_header("@@ -78,7 +78,8 @@ class JumpGate:")  ->  (78, 7, 78, 8)
               hunk_header("@@ -5 +5,2 @@")                      ->  (5, 1, 5, 2)
    """
    return None   # TODO: write your code above, and return the result


# TODO 2 ------------------------------------------------------------------------------------
def diff_stat(patch_text):
    """How many lines a patch adds and removes in each file (lesson §3), like `git apply --numstat`.

    patch_text: the whole text of a patch made by `git diff` (one string, many lines).
    Returns a dict {path: (added, removed)}. The path of a file is the one after " b/" on its
    "diff --git" line. The header lines of a file (diff --git, index, --- a/…, +++ b/…) are not changes.

    Example:  diff_stat(EXAMPLE_PATCH)  ->  {"README.md": (2, 0), "navera_lite.yaml": (1, 1)}
    """
    return None   # TODO: write your code above, and return the result


# TODO 3 ------------------------------------------------------------------------------------
def first_bad(commits, is_bad):
    """The first bad commit, found by binary search (lesson §4), as git bisect does.

    commits: the suspects, oldest first (hashes, numbers… any values). The LAST one is known to be bad,
             and the commit just before the first one is known to be good. One change made the code bad:
             every commit before the first bad one is good, every commit from it on is bad.
    is_bad:  a function. is_bad(c) runs the test on commit c: True = bad, False = good. Each call is one
             test run, so call it at most ⌈log₂ len(commits)⌉ times, and never on the last commit.
    Returns the first bad commit (one element of commits).

    Example:  first_bad(list(range(1, 17)), lambda c: c >= 11)  ->  11      (4 calls to is_bad)
    """
    return None   # TODO: write your code above, and return the result


if __name__ == "__main__":
    print("detective.py is a module: run   python3 run_lab.py test")
