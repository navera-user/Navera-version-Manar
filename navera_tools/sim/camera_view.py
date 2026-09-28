"""Simulated camera image: the onboard map rendered under the vehicle.

For the simulator's camera panel only. The picture is cut from the same
satellite map NAVERA matches against, so it is NOT a test of vision accuracy
(a real camera sees a different day, season, angle and sensor).
"""
import io
import math

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

TILE = 256


def _xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


class CameraView:
    def __init__(self, tiles, zoom=17, size=(480, 320)):
        self.tiles = tiles            # simulation_web.web_common.MBTilesReader
        self.zoom = zoom
        self.size = size

    def _mosaic(self, lat, lon, z, half):
        x, y = _xy(lat, lon, z)
        tx, ty = int(x), int(y)
        img = Image.new("RGB", ((2 * half + 1) * TILE,) * 2, (12, 16, 22))
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                data = self.tiles.get(z, tx + dx, ty + dy)
                if data:
                    try:
                        t = Image.open(io.BytesIO(data)).convert("RGB")
                        img.paste(t, ((dx + half) * TILE, (dy + half) * TILE))
                    except Exception:
                        pass
        cx = (x - tx + half) * TILE
        cy = (y - ty + half) * TILE
        return img, cx, cy

    def render(self, lat, lon, heading_deg, night=False, failed=False):
        w, h = self.size
        if failed:
            img = Image.effect_noise((w, h), 60).convert("RGB")
            return self._jpeg(img)
        img, cx, cy = self._mosaic(lat, lon, self.zoom, 1)
        r = int(math.hypot(w, h) / 2) + 2
        img = img.crop((int(cx) - r, int(cy) - r, int(cx) + r, int(cy) + r))
        img = img.rotate(heading_deg, resample=Image.BILINEAR)     # heading up
        img = img.crop((r - w // 2, r - h // 2, r - w // 2 + w, r - h // 2 + h))
        if night:           # thermal-like: grey, contrast-stretched, soft, grainy
            g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=2)
            g = ImageEnhance.Brightness(g.filter(ImageFilter.GaussianBlur(1.2))).enhance(0.85)
            noise = Image.effect_noise((w, h), 18)
            img = Image.blend(g, noise, 0.12).convert("RGB")
        return self._jpeg(img)

    @staticmethod
    def _jpeg(img):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=78)
        return buf.getvalue()
