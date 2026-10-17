"""The Insta360's full 360 stream as a bench camera: finds the screen it faces and gives a straight
view centred on it, the camera's own gravity, and the stream delay measured on the screen.

Used by screen_flight.py --source 360. The screen is found by flashing it white then black and
taking the difference in the 360 frame; the lens that sees it, the direction of its centre and
its angular size come out of that (the size checks the lens focal length guess against the
screen's real width and distance). The stream delay (1.5 s, key frames only) was measured
separately by toggling the screen and is passed to the bench as its latency.
"""
import math
import time

import cv2
import numpy as np

from navera_tools.field import allsky
from navera_tools.field.insta360_usb import Insta360Usb
from navera_tools.field.sky360 import PinholeView, default_lenses


class Bench360:
    def __init__(self, window: str, screen_wh=(1920, 1080)):
        self.cam = Insta360Usb()
        self.window, self.screen_wh = window, screen_wh
        self.view = None
        self.info = {}

    def _frame(self, timeout=20.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            f, t = self.cam.latest()
            if f is not None and time.time() - t < 0.5:
                return f, t
            cv2.waitKey(30)
        raise RuntimeError(f"no frame from the 360 camera: {self.cam.error}")

    def _show(self, value, secs):
        img = np.full((self.screen_wh[1], self.screen_wh[0], 3), value, np.uint8)
        cv2.imshow(self.window, img)
        t_shown = time.time()
        end = t_shown + secs
        while time.time() < end:
            cv2.waitKey(20)
        return t_shown

    def _settled(self, value, secs=3.0):
        """Show a flat screen, wait out the stream delay (~1.5 s), return the newest grey frame."""
        self._show(value, secs)
        return cv2.cvtColor(self._frame()[0], cv2.COLOR_BGR2GRAY).astype(np.float32)

    def find_screen(self, hfov_deg=100.0, width=1200, height=900, screen_mm=None, distance_mm=None):
        """Flash the screen black-white-black, locate it, build the straight view on it; returns what it measured.
        Only what brightened with white and darkened again counts (people moving in the room do not), and the
        result must be a plausible screen (one compact bright region 20-95 degrees wide)."""
        self._frame()
        self._show(0, 2.0)                                   # the new window settles
        black1 = self._settled(0)
        white = self._settled(255)
        black2 = self._settled(0)
        diff = cv2.GaussianBlur(np.minimum(white - black1, white - black2), (0, 0), 3)
        mask = (diff > max(25.0, 0.5 * float(np.percentile(diff, 99.5)))).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
        if n < 2:
            raise RuntimeError("the screen was not seen by the 360 camera (is a lens facing it?)")
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y = cent[k]
        lens = min(default_lenses(), key=lambda L: math.hypot(x - L.cx, y - L.cy))
        fwd = allsky.unproject(lens, x, y)
        up, _, _ = self.cam.gravity()
        up = up if up is not None else np.array([1.0, 0.0, 0.0])
        self.view = PinholeView(lens, fwd, up, hfov_deg, width, height)
        # angular width of the screen, in the straight view (the screen's edges look dimmer at an angle:
        # Otsu on the flash difference keeps all of it)
        d = self.view.apply(np.clip(diff, 0, 255).astype(np.uint8))
        _, m = cv2.threshold(cv2.GaussianBlur(d, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(m)
        k2 = 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA]))
        xs = np.nonzero(lab2[height // 2] == k2)[0]
        c, fv = (width - 1) / 2.0, self.view.f
        width_deg = math.degrees(math.atan((xs.max() - c) / fv) - math.atan((xs.min() - c) / fv)) if len(xs) else float("nan")
        self.info = {"lens": lens.name, "screen_centre_px": [round(float(x)), round(float(y))],
                     "off_lens_axis_deg": round(math.degrees(math.acos(float(np.clip(fwd @ lens.R_lens_imu[2], -1, 1)))), 1),
                     "screen_width_deg": round(width_deg, 1)}
        if screen_mm and distance_mm:
            expect = 2 * math.degrees(math.atan(screen_mm / 2 / distance_mm))
            self.info["screen_width_expected_deg"] = round(expect, 1)
            self.info["focal_check"] = round(width_deg / expect, 3)       # 1.0 = the lens guess matches
        if not 20.0 <= width_deg <= 95.0:
            raise RuntimeError(f"screen not found reliably ({self.info}); is a lens facing it, nothing moving in front?")
        return self.info

    def grab(self):
        """(straight view on the screen, Jetson arrival time) or (None, t)."""
        f, t = self.cam.latest()
        if f is None or self.view is None:
            return None, t
        return self.view.apply(f), t

    def gravity(self):
        return self.cam.gravity()

    def close(self):
        self.cam.close()
