"""IMU driver behaviour with a simulated BNO085 (no hardware, no Adafruit stack).

The Blinka / adafruit_bno08x modules are replaced by stand-ins so the node's
own logic can be exercised: publishing, frozen-data detection, re-init.
"""
import sys
import types

import pytest
import rclpy


class FakeBNO:
    """Stand-in BNO08X_I2C. mode 'noisy' changes every read, 'frozen' never does."""
    instances = []

    def __init__(self, i2c, address=0x4A):
        self.mode = "noisy"
        self.n = 0
        FakeBNO.instances.append(self)

    def enable_feature(self, feature):
        pass

    def _v(self, base):
        if self.mode == "noisy":
            self.n += 1
            return tuple(b + 1e-4 * self.n for b in base)
        return base

    @property
    def quaternion(self):
        return self._v((0.0, 0.0, 0.0, 1.0))

    @property
    def gyro(self):
        return self._v((0.01, 0.0, 0.0))

    @property
    def linear_acceleration(self):
        return self._v((0.0, 0.0, 0.1))

    acceleration = linear_acceleration


class FakeI2C:
    deinit_calls = 0

    def __init__(self, scl, sda):
        pass

    def deinit(self):
        FakeI2C.deinit_calls += 1


@pytest.fixture(scope="module")
def imu_module():
    board = types.ModuleType("board")
    board.SCL_1 = board.SDA_1 = board.SCL = board.SDA = object()
    busio = types.ModuleType("busio")
    busio.I2C = FakeI2C
    bno = types.ModuleType("adafruit_bno08x")
    for name in ("BNO_REPORT_ACCELEROMETER", "BNO_REPORT_GYROSCOPE",
                 "BNO_REPORT_LINEAR_ACCELERATION", "BNO_REPORT_ROTATION_VECTOR"):
        setattr(bno, name, name)
    bno_i2c = types.ModuleType("adafruit_bno08x.i2c")
    bno_i2c.BNO08X_I2C = FakeBNO
    sys.modules.update({"board": board, "busio": busio,
                        "adafruit_bno08x": bno, "adafruit_bno08x.i2c": bno_i2c})
    from imu_pkg.nodes import imu_node
    rclpy.init()
    yield imu_node
    rclpy.shutdown()


def test_noisy_data_is_published_and_frozen_data_is_not(imu_module):
    node = imu_module.IMUNode()
    published = []
    node.pub_imu.publish = published.append
    try:
        for _ in range(20):
            node.publish_imu()
        assert len(published) == 20

        FakeBNO.instances[-1].mode = "frozen"
        before = len(published)
        n = imu_module._MAX_FROZEN_SAMPLES
        # Read 1 is a new value; reads 2..n repeat it (cannot tell yet); read
        # n+1 is the n-th repeat → frozen: not published, re-init requested.
        for _ in range(n + 1):
            node.publish_imu()
        assert len(published) - before == n
        assert node.bno is None
    finally:
        node.destroy_node()


def test_reconnect_is_rate_limited(imu_module):
    node = imu_module.IMUNode()
    try:
        node.bno = None
        created = len(FakeBNO.instances)
        for _ in range(50):                          # 50 ticks in a row
            node.publish_imu()
        assert len(FakeBNO.instances) - created <= 1  # at most one attempt per period
        assert FakeI2C.deinit_calls >= 1             # previous bus handle released
    finally:
        node.destroy_node()
