"""A camera read through GStreamer directly, with the cv2.VideoCapture calls live_camera
uses (isOpened, grab, retrieve, read, release).

The Jetson's CSI cameras are only reachable through GStreamer (nvarguscamerasrc), and the
OpenCV wheel on the box is built without GStreamer: cv2.CAP_GSTREAMER cannot open them.
This uses the system's GStreamer through its Python bindings (gi) instead.
"""
import os
import re

import numpy as np

SECRETS = ("NAVERA_IP_CAMERA_USER", "NAVERA_IP_CAMERA_PASSWORD")


def expand_secrets(pipeline: str, environ=None) -> str:
    """The pipeline with @NAVERA_IP_CAMERA_USER@ / @NAVERA_IP_CAMERA_PASSWORD@ replaced by their values
    (quoted for gst_parse_launch). navera_common.cameras writes the names, never the password, into
    discovered.env and the discovery report; the node fills them in here, at start. (@...@, not $...:
    a systemd EnvironmentFile or a shell sourcing the file must not expand them.)"""
    env = os.environ if environ is None else environ

    def value(m):
        v = str(env.get(m.group(1), "") or "")
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return re.sub("@(" + "|".join(SECRETS) + ")@", value, pipeline)


def csi_pipeline(width: int, height: int, sensor_id: int = 0, fps: int = 30) -> str:
    return (f"nvarguscamerasrc sensor-id={sensor_id} ! "
            f"video/x-raw(memory:NVMM),width={width},height={height},framerate={fps}/1 ! "
            f"nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! "
            f"appsink name=sink drop=true max-buffers=1 sync=false")


class GstCapture:
    def __init__(self, pipeline: str, timeout_s: float = 2.0):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self._Gst, self._timeout = Gst, int(timeout_s * Gst.SECOND)
        self._sample = None
        self.stamps = None                                  # (arrival s, source PTS s) of the last grab
        try:
            self._pipe = Gst.parse_launch(pipeline)
            self._sink = self._pipe.get_by_name("sink")
        except Exception:                                   # noqa: BLE001 — bad pipeline string
            self._pipe = self._sink = None
            return
        if self._sink is None or self._pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.release()

    def isOpened(self) -> bool:                             # noqa: N802 — cv2.VideoCapture's name
        return self._pipe is not None

    def grab(self) -> bool:
        """Wait for the next frame (paced by the camera), without converting it."""
        if self._pipe is None:
            return False
        self._sample = self._sink.emit("try-pull-sample", self._timeout)
        self.stamps = None
        if self._sample is not None:
            # (arrival, source stamp) in the pipeline's running time: the buffer PTS was set where the
            # frame entered (the sensor, the RTP receiver); their difference is the queueing after it
            try:
                pts = self._sample.get_buffer().pts
                clock = self._pipe.get_clock()
                if pts != self._Gst.CLOCK_TIME_NONE and clock is not None:
                    self.stamps = ((clock.get_time() - self._pipe.get_base_time()) / 1e9, pts / 1e9)
            except Exception:                               # noqa: BLE001 — stamps are optional
                self.stamps = None
        return self._sample is not None

    def retrieve(self):
        """(ok, BGR image) of the last grabbed frame."""
        s, self._sample = self._sample, None
        if s is None:
            return False, None
        caps = s.get_caps().get_structure(0)
        w, h = caps.get_value("width"), caps.get_value("height")
        buf = s.get_buffer()
        ok, info = buf.map(self._Gst.MapFlags.READ)
        if not ok:
            return False, None
        try:
            stride = info.size // h                     # rows are padded to 4 bytes
            img = np.ndarray((h, w, 3), np.uint8, info.data, strides=(stride, 3, 1)).copy()
        finally:
            buf.unmap(info)
        return True, img

    def read(self):
        return self.retrieve() if self.grab() else (False, None)

    def release(self) -> None:
        if self._pipe is not None:
            self._pipe.set_state(self._Gst.State.NULL)
        self._pipe = self._sink = None
