"""Pair camera images with their frame_meta.

camera_publisher publishes each frame as two messages: the Image and a JSON
frame_meta. Pairing them as "latest image + latest meta" breaks for the rest
of a mission as soon as one of the two is lost: every later image gets the
previous frame's metadata (position truth, heading, frame id). The camera now
writes its image's header stamp into the meta ("image_stamp_ns"), and pairs are
matched on that exact stamp.
"""
import threading
from collections import OrderedDict
from typing import Any, Optional, Tuple


def stamp_ns(stamp) -> int:
    """builtin_interfaces/Time → integer nanoseconds."""
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def exposure_stamp(meta, fallback):
    """The frame's measurement instant (its image stamp) as a Time message.

    `fallback` (a builtin_interfaces/Time) is returned when the meta carries
    no stamp (older camera).
    """
    from builtin_interfaces.msg import Time
    ns = meta.get("image_stamp_ns") if isinstance(meta, dict) else None
    if ns is None:
        return fallback
    ns = int(ns)
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


class FramePairer:
    """Thread-safe image/meta matcher.

    add_image / add_meta return (image, meta) when a pair is complete, else
    None. The image is None when the camera reported it could not load the
    file (meta["image_missing"]) or the subscriber could not decode it: the
    frame is still returned so it can be acknowledged and declared invalid.
    Metas without "image_stamp_ns" (older camera) fall back to latest-of-each.
    """

    def __init__(self, max_pending: int = 8):
        self._max = max_pending
        self._images: "OrderedDict[int, Any]" = OrderedDict()
        self._metas: "OrderedDict[int, dict]" = OrderedDict()
        self._legacy_image: Optional[Any] = None
        self._legacy_meta: Optional[dict] = None
        self._lock = threading.Lock()

    def _trim(self, d: OrderedDict) -> None:
        while len(d) > self._max:
            d.popitem(last=False)

    def add_image(self, stamp: int, image) -> Optional[Tuple[Any, dict]]:
        with self._lock:
            meta = self._metas.pop(stamp, None)
            if meta is not None:
                return image, meta
            if self._legacy_meta is not None:
                meta, self._legacy_meta = self._legacy_meta, None
                return image, meta
            self._images[stamp] = image
            self._legacy_image = image
            self._trim(self._images)
            return None

    def add_meta(self, meta: dict) -> Optional[Tuple[Any, dict]]:
        with self._lock:
            stamp = meta.get("image_stamp_ns")
            if stamp is None:                       # older camera: latest-of-each
                if self._legacy_image is not None:
                    image, self._legacy_image = self._legacy_image, None
                    self._images.clear()
                    return image, meta
                self._legacy_meta = meta
                return None
            stamp = int(stamp)
            if meta.get("image_missing"):
                self._images.pop(stamp, None)
                return None, meta
            if stamp in self._images:
                image = self._images.pop(stamp)
                if self._legacy_image is image:
                    self._legacy_image = None
                return image, meta
            self._metas[stamp] = meta
            self._trim(self._metas)
            return None
