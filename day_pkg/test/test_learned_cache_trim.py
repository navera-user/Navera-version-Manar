"""learned_matcher._trim_cache: PyTorch's CUDA cache (system memory on the Jetson) is emptied after a
wide window or when it holds more than CACHE_SLACK_MIB unused (60-min soak 2026-10-23: reserved
1.3 -> 2.5 GB for ~90 MiB allocated, day node 4.2 GB RSS + swap; 7-min A/B 4.2 -> 2.4 GB)."""
from types import SimpleNamespace

from day_pkg.learned_matcher import LearnedMatcher


def _m(reserved_mib, alloc_mib):
    calls = []
    cuda = SimpleNamespace(memory_reserved=lambda: reserved_mib * 2 ** 20,
                           memory_allocated=lambda: alloc_mib * 2 ** 20,
                           empty_cache=lambda: calls.append(1))
    m = LearnedMatcher.__new__(LearnedMatcher)
    m._t = SimpleNamespace(cuda=cuda)
    return m, calls


def test_cache_kept_while_small():
    m, calls = _m(300.0, 90.0)
    m._trim_cache(150.0)
    assert not calls


def test_cache_emptied_when_it_piles_up_or_after_a_wide_window():
    m, calls = _m(2474.0, 90.0)
    m._trim_cache(150.0)
    assert calls
    m, calls = _m(100.0, 90.0)
    m._trim_cache(600.0)
    assert calls
