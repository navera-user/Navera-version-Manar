"""A GigE Vision / USB3 Vision (GenICam) camera read through Aravis, with the cv2.VideoCapture calls
live_camera uses (isOpened, grab, retrieve, read, release).

Industrial cameras (Basler, Teledyne FLIR, Allied Vision, Hikrobot, Daheng, Lucid, FLIR A-series
thermal...) speak GenICam, not V4L2: OpenCV cannot open them and the makers' SDKs are closed and
per brand. Aravis (open source, apt: gir1.2-aravis-0.8) reads them all.

The picture comes as the camera sends it: colour (RGB8 / BGR8 / YUV 4:2:2), raw Bayer (debayered
here), or grey (Mono8 / Mono10-16 unpacked: thermal cores give 16 bit, stretched to 8 bit by
live_camera.to_bgr8). A camera set to a packed or other format is switched to the first of these
it offers. Exposure and gain are set to automatic where the camera has them (GenICam names).
"""
import numpy as np

# GenICam pixel format numbers (PFNC)
MONO8, MONO10, MONO12, MONO16 = 0x01080001, 0x01100003, 0x01100005, 0x01100007
BAYER = {0x01080008: "GR", 0x01080009: "RG", 0x0108000A: "GB", 0x0108000B: "BG"}
RGB8, BGR8, YUV422_UYVY, YUV422_YUYV = 0x02180014, 0x02180015, 0x0210001F, 0x02100032
READABLE = ("BGR8", "RGB8", "BayerRG8", "BayerGR8", "BayerGB8", "BayerBG8", "YUV422_8_UYVY", "YUV422_8",
            "Mono16", "Mono12", "Mono10", "Mono8")
# OpenCV names a Bayer pattern by its second row: GenICam RG (R G / G B) is OpenCV's BG
_CV_BAYER = {"RG": "COLOR_BayerBG2BGR", "GR": "COLOR_BayerGB2BGR", "GB": "COLOR_BayerGR2BGR", "BG": "COLOR_BayerRG2BGR"}


def load_aravis():
    import gi
    gi.require_version("Aravis", "0.8")
    from gi.repository import Aravis
    return Aravis


def to_image(data: bytes, w: int, h: int, fmt: int):
    """The frame as numpy: BGR for colour, 2-D for grey (uint8 or uint16), None for a format not read."""
    import cv2
    if fmt == MONO8:
        return np.frombuffer(data, np.uint8, w * h).reshape(h, w).copy()
    if fmt in (MONO10, MONO12, MONO16):
        return np.frombuffer(data, "<u2", w * h).reshape(h, w).copy()
    if fmt in BAYER:
        raw = np.frombuffer(data, np.uint8, w * h).reshape(h, w)
        return cv2.cvtColor(raw, getattr(cv2, _CV_BAYER[BAYER[fmt]]))
    if fmt in (RGB8, BGR8):
        img = np.frombuffer(data, np.uint8, w * h * 3).reshape(h, w, 3)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if fmt == RGB8 else img.copy()
    if fmt in (YUV422_UYVY, YUV422_YUYV):
        img = np.frombuffer(data, np.uint8, w * h * 2).reshape(h, w, 2)
        return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_UYVY if fmt == YUV422_UYVY else cv2.COLOR_YUV2BGR_YUY2)
    return None


class AravisCapture:
    def __init__(self, device_id: str = "", timeout_s: float = 2.0, width: int = 0, height: int = 0,
                 aravis=None, buffers: int = 4):
        self._timeout_us = int(timeout_s * 1e6)
        self._buf = None
        self.stamps = None
        self.error = ""
        self._cam = self._stream = None
        try:
            ar = aravis if aravis is not None else load_aravis()
        except (ImportError, ValueError) as e:
            self.error = f"Aravis is not installed ({e}): sudo apt install gir1.2-aravis-0.8 aravis-tools"
            return
        self._ar = ar
        try:
            cam = ar.Camera.new(device_id or None)
            self._choose_format(cam)
            if width > 0 and height > 0:
                try:
                    cam.set_region(0, 0, width, height)
                except Exception:                           # noqa: BLE001 — keep the camera's own size
                    pass
            for feature in ("ExposureAuto", "GainAuto"):
                try:
                    cam.set_string(feature, "Continuous")
                except Exception:                           # noqa: BLE001 — not every camera has them
                    pass
            try:
                if cam.is_gv_device():
                    cam.gv_auto_packet_size()               # the largest packet the link carries
            except Exception:                               # noqa: BLE001
                pass
            cam.set_acquisition_mode(ar.AcquisitionMode.CONTINUOUS)
            stream = cam.create_stream(None, None)
            size = cam.get_payload()
            for _ in range(buffers):
                stream.push_buffer(ar.Buffer.new_allocate(size))
            cam.start_acquisition()
            self._cam, self._stream = cam, stream
        except Exception as e:                              # noqa: BLE001 — no such camera, busy...
            self.error = str(e)

    @staticmethod
    def _choose_format(cam) -> None:
        try:
            now = cam.get_pixel_format_as_string()
            offered = list(cam.dup_available_pixel_formats_as_strings() or [])
        except Exception:                                   # noqa: BLE001
            return
        if now in READABLE:
            return
        for f in READABLE:
            if f in offered:
                try:
                    cam.set_pixel_format_from_string(f)
                    return
                except Exception:                           # noqa: BLE001
                    continue

    def isOpened(self) -> bool:                             # noqa: N802 — cv2.VideoCapture's name
        return self._cam is not None

    def grab(self) -> bool:
        if self._cam is None:
            return False
        if self._buf is not None:                           # the previous frame, not retrieved
            self._stream.push_buffer(self._buf)
            self._buf = None
        buf = self._stream.timeout_pop_buffer(self._timeout_us)
        if buf is None:
            return False
        if buf.get_status() != self._ar.BufferStatus.SUCCESS:
            self._stream.push_buffer(buf)                   # a frame with lost packets
            return False
        self._buf = buf
        return True

    def retrieve(self):
        buf, self._buf = self._buf, None
        if buf is None:
            return False, None
        try:
            img = to_image(bytes(buf.get_data()), buf.get_image_width(), buf.get_image_height(),
                           int(buf.get_image_pixel_format()))
        finally:
            self._stream.push_buffer(buf)
        return (img is not None), img

    def read(self):
        return self.retrieve() if self.grab() else (False, None)

    def release(self) -> None:
        if self._cam is not None:
            try:
                self._cam.stop_acquisition()
            except Exception:                               # noqa: BLE001
                pass
        self._cam = self._stream = self._buf = None
