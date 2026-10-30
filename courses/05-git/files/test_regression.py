"""tests/test_regression.py — a test that would have caught the regression (lab Step 8, TODO 5).

Copy this file into the repository (from inside navera-lite-history):   cp ../test_regression.py tests/
pytest runs every function whose name starts with test_. A test passes when none of its asserts fails.
"""
from navera_lite.guard import JumpGate


# TODO 5 ------------------------------------------------------------------------------------------
def test_gate_widens_after_a_jump():
    """Lesson 1's table on JumpGate(100.0, 50.0): a trusted fix at (0, 0) at t = 0 s, then the table's 7 rows,
    one fix per second: six fixes at (500, 0), then one at (900, 0): 8 fixes in all. Assert what the
    gate must answer for EACH fix (check() returns True for accepted), so that a gate that never widens
    fails this test.

    Example of the tool:  gate = JumpGate(100.0, 50.0);  gate.check(0.0, (0, 0))  ->  True
    """
    raise NotImplementedError("TODO 5")
