"""navera_common.memory_trim: malloc_trim at most once per period, RSS reported."""
import numpy as np

from navera_common import memory_trim


def test_trim_gives_back_freed_heap_memory():
    blocks = [np.ones(100_000, np.uint8) for _ in range(3000)]     # ~300 MB in small heap blocks
    before = memory_trim.rss_mib()
    del blocks
    t = memory_trim.Trimmer(period_s=60.0)
    assert t.maybe_trim(now=0.0)
    assert t.last_ms is not None and t.last_ms < 2000
    assert memory_trim.rss_mib() < before - 100                     # glibc kept them until the trim


def test_period_and_off():
    t = memory_trim.Trimmer(period_s=60.0)
    assert t.maybe_trim(now=100.0) and not t.maybe_trim(now=130.0) and t.maybe_trim(now=161.0)
    assert not memory_trim.Trimmer(period_s=0.0).maybe_trim(now=0.0)
