"""Share the one Jetson GPU between every student: at most N trainings at once, and few CPU threads.

    from academy_gpu import torch_device
    with torch_device() as device:          # waits for a free GPU slot (or uses the CPU)
        model.to(device); ...train...

The platform gives every sandbox the same slot folder (env ACADEMY_GPU_SLOTS="folder:N"). A slot is a lock
file held with flock while the block runs; the lock goes away by itself when the process ends, even after
Ctrl+C or a crash. Outside the academy (no ACADEMY_GPU_SLOTS) the GPU is used freely.
"""
import contextlib
import fcntl
import os
import sys
import time

CPU_THREADS = 2          # measured 2026-10-15: 6 threads per process made a busy Jetson ~12x slower


def limit_threads(n=CPU_THREADS):
    """Use at most n CPU threads in torch (call once, before any work)."""
    try:
        import torch
        torch.set_num_threads(n)
    except Exception:
        pass


@contextlib.contextmanager
def gpu_slot(wait_s=600.0, quiet=False):
    """Hold one of the shared GPU slots while the block runs; yields True, or False if no GPU slot was free
    within wait_s seconds (then use the CPU)."""
    spec = os.environ.get("ACADEMY_GPU_SLOTS", "")
    if not spec:
        yield True
        return
    folder, _, n = spec.rpartition(":")
    n = max(1, int(n or 1))
    why = flight_lock()
    if why:
        raise FlightLock(f"AI training is refused right now: {why}. Run it again once the vehicle has landed.")
    deadline, told = time.monotonic() + wait_s, False
    while True:
        for i in range(n):
            f = open(os.path.join(folder, f"slot{i}"), "a")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                f.close()
                continue
            try:
                yield True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()
            return
        if time.monotonic() >= deadline:
            yield False
            return
        if not told and not quiet:
            print(f"The GPU is busy ({n} GPU job{'s' if n != 1 else ''} already running in the class): waiting for a "
                  f"free slot (up to {wait_s / 60:.0f} min)…", file=sys.stderr, flush=True)
            told = True
        time.sleep(2.0)


class FlightLock(RuntimeError):
    """NAVERA (on the same box) is flying, or cannot tell: GPU/AI training is refused until it has landed."""


def flight_lock():
    """The platform's reason to refuse GPU work now (file FLIGHT_LOCK in the slot folder), or None."""
    folder = os.environ.get("ACADEMY_GPU_SLOTS", "").rpartition(":")[0]
    try:
        with open(os.path.join(folder, "FLIGHT_LOCK")) as f:
            return f.read().strip() or "NAVERA is flying"
    except OSError:
        return None


class NoGpuSlot(RuntimeError):
    """No GPU slot came free in time and the mission said the CPU is not an option."""


@contextlib.contextmanager
def torch_device(wait_s=3600.0, quiet=False, cpu_ok=True):
    """"cuda" while holding a GPU slot, else "cpu" (no GPU, or none free within wait_s). Also limits threads.

    cpu_ok=False (a training too slow for the CPU): instead of falling back, raise NoGpuSlot with a clear
    message, so the student retries later rather than training for hours."""
    why = flight_lock()
    if why:
        raise FlightLock(f"AI training is refused right now: {why}. Run it again once the vehicle has landed.")
    limit_threads()
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except Exception:
        has_gpu = False
    if not has_gpu:
        yield "cpu"
        return
    with gpu_slot(wait_s, quiet) as ok:
        if not ok and not cpu_ok:
            raise NoGpuSlot(f"No GPU slot came free in {wait_s / 60:.0f} min (the class is training). This job is too "
                            "slow for the CPU: run the same command again a bit later, or ask your teacher.")
        if not ok and not quiet:
            print("No GPU slot came free: training on the CPU (slower).", file=sys.stderr, flush=True)
        yield "cuda" if ok else "cpu"
        if ok:
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
