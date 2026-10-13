"""polling.py — reproduce a real bug without ROS: a messenger that POLLS at 5 Hz while positions ARRIVE at 5 Hz.

Positions arrive about every 0.2 s, never exactly (their arrival time jitters). The messenger forwards
positions to the autopilot in one of two ways:
  poll     a timer ticks poll_hz times a second and forwards the LATEST position it has (NAVERA before the fix)
  arrival  it forwards each position the moment it arrives, from the subscription's callback (after the fix)

    python3 polling.py                          poll at 5 Hz, jitter 40 ms (the defaults)
    python3 polling.py --jitter-ms 0            a perfect clock on the sender's side
    python3 polling.py --poll-hz 10             poll twice as fast
    python3 polling.py --mode arrival           forward on arrival

It counts, over 60 s (300 positions): DROPPED = positions never forwarded; DOUBLED = ticks that forwarded a
position the autopilot had already received; and the longest time the autopilot waited for a new position.
"""
import argparse
import random

# ---- you don't need to change anything in this file (but you can read it!) ----

RATE_HZ = 5.0           # positions per second
N = 300                 # 60 s of positions
SEED = 5


def arrivals(jitter_ms, seed=SEED):
    """Arrival times (s) of the N positions: k / RATE_HZ plus a Gaussian jitter, kept in order."""
    rng = random.Random(seed)
    out, last = [], -1.0
    for k in range(N):
        t = k / RATE_HZ + 0.5 + rng.gauss(0.0, jitter_ms / 1000.0)
        last = max(t, last + 1e-4)          # a later position never arrives before an earlier one
        out.append(last)
    return out


def forward_by_polling(times, poll_hz, phase_ms):
    """The ticks' choices: for each tick, the index of the latest position arrived (None before the first)."""
    sent, tick, k = [], phase_ms / 1000.0, -1
    end = times[-1] + 1.0 / poll_hz
    while tick <= end:
        while k + 1 < len(times) and times[k + 1] <= tick:
            k += 1
        sent.append((tick, k if k >= 0 else None))
        tick += 1.0 / poll_hz
    return sent


def count(sent, n):
    """(dropped, doubled, longest wait in s) for a list of (time, index or None) sends."""
    seen, doubled, last_new, longest = set(), 0, None, 0.0
    for t, k in sent:
        if k is None:
            continue
        if k in seen:
            doubled += 1
            continue
        seen.add(k)
        if last_new is not None:
            longest = max(longest, t - last_new)
        last_new = t
    return n - len(seen), doubled, longest


def main():
    ap = argparse.ArgumentParser(description="poll vs on-arrival forwarding (no ROS)")
    ap.add_argument("--mode", choices=("poll", "arrival"), default="poll")
    ap.add_argument("--poll-hz", type=float, default=5.0)
    ap.add_argument("--jitter-ms", type=float, default=40.0)
    ap.add_argument("--phase-ms", type=float, default=150.0, help="when the first tick happens (ms)")
    a = ap.parse_args()
    times = arrivals(a.jitter_ms)
    if a.mode == "arrival":
        sent = [(t, k) for k, t in enumerate(times)]
        how = "forwarded on arrival"
    else:
        sent = forward_by_polling(times, a.poll_hz, a.phase_ms)
        how = f"polled at {a.poll_hz:g} Hz"
    dropped, doubled, longest = count(sent, len(times))
    print(f"{len(times)} positions at {RATE_HZ:g} Hz (jitter {a.jitter_ms:g} ms), {how}: "
          f"{len(sent)} messages sent to the autopilot")
    print(f"  DROPPED  {dropped:4d}   positions the autopilot never received")
    print(f"  DOUBLED  {doubled:4d}   messages that repeated a position it already had")
    print(f"  longest wait for a new position: {longest * 1000:.0f} ms")
    if a.mode == "poll":
        rows = [(t, k) for t, k in sent if k is not None][:12]
        line = []
        prev = None
        for t, k in rows:
            if prev is not None and k == prev:
                line.append(f"#{k}(again)")
            elif prev is not None and k > prev + 1:
                line.append(f"#{k}(#{prev + 1} lost)" if k == prev + 2 else f"#{k}({k - prev - 1} lost)")
            else:
                line.append(f"#{k}")
            prev = k
        print("  first ticks sent: " + " ".join(line))


if __name__ == "__main__":
    main()
