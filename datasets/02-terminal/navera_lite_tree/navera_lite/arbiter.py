"""navera_lite/arbiter.py — the judge: which source to trust, and the state.

Part of NAVERA Lite, the course's teaching stack (mission 29). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 29.
"""


def candidates(latest, now_s, cfg):
    """Eligible sources in priority order."""
    ...


def pick(cands, current, since, now_s, cfg):
    """The winner, with the hold-off."""
    ...


def decide(latest, now_s, mem, cfg):
    """One decision: state, source, reason."""
    ...
