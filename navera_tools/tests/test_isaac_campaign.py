#!/usr/bin/env python3
"""The Isaac Sim campaign appends --extra to a condition's arguments once (it did twice). Exit code 0 = pass."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "isaac"))
import campaign  # noqa: E402


def main():
    a = campaign.condition_args("outage60", "--set EK3_GLITCH_RAD=25 --day-args '-p x:=1'")
    ok = a.count("--set") == 1 and a.count("--day-args") == 1 and a.startswith(campaign.CONDITIONS["outage60"][1])
    ok = ok and campaign.condition_args("base") == campaign.CONDITIONS["base"][1]
    print("PASS" if ok else f"FAIL: {a}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
