"""Shared pytest configuration of navera_tools/tests."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "perf: offline accuracy benchmark on recorded data (minutes, GPU); "
                   "runs only with NAVERA_PERF=1, deselect with -m 'not perf'")
