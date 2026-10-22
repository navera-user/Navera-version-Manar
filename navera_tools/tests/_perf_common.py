"""Skip rules shared by the accuracy benchmarks (test_perf_*.py): never a silent pass."""
import os

import pytest


def require_perf(paths) -> None:
    """Skip, with the reason, unless NAVERA_PERF=1, a CUDA GPU and every data path are there."""
    if os.environ.get("NAVERA_PERF") != "1":
        pytest.skip("accuracy benchmark (minutes on the GPU): set NAVERA_PERF=1 to run it "
                    "(wrap in flock /tmp/claude-1000/navera_gpu.lock on the shared Jetson)")
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        pytest.skip("benchmark data missing: " + ", ".join(missing))
    try:
        import torch
        gpu = torch.cuda.is_available()
    except ImportError:
        gpu = False
    if not gpu:
        pytest.skip("benchmark needs a CUDA GPU (the product matcher's device)")
