# Lesson 17 — the camera as a measuring tool.
# Fill in the TODOs, save (Ctrl+S), then run:   python3 camera_math.py
#
# Angles are given in DEGREES. Python's math.tan() wants RADIANS: use math.radians(deg).
# Heights and sizes are in meters, image sizes in pixels.
import math

EARTH_CIRCUMFERENCE_M = 40075016.7     # the same constant as NAVERA's day_pkg (EQUATOR_M)
TILE_PX = 256                          # a map tile is 256 x 256 pixels (lesson 7)


# ---------------------------------------------------------------- TODO 1
def focal_px(hfov_deg, width_px):
    """Focal length in pixels of a pinhole camera that sees hfov_deg across width_px pixels.
    f = (width_px / 2) / tan(hfov / 2)"""
    return (width_px / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


def footprint(height_m, hfov_deg):
    """Width (m) of the ground seen by a camera looking straight down from height_m.
    W = 2 * h * tan(hfov / 2)"""
    return 2.0 * height_m * math.tan(math.radians(hfov_deg) / 2.0)


def meters_per_pixel(height_m, hfov_deg, width_px):
    """Ground meters covered by one pixel (the footprint spread over the picture width)."""
    return footprint(height_m, hfov_deg) / width_px


# ---------------------------------------------------------------- TODO 2
def height_from_object(size_m, size_px, hfov_deg, width_px):
    """Height (m) of a straight-down camera that sees an object of size_m meters
    as size_px pixels.  Pinhole rule:  size_px / f = size_m / h"""
    return size_m * focal_px(hfov_deg, width_px) / size_px


# ---------------------------------------------------------------- TODO 3
def map_meters_per_pixel(lat_deg, zoom):
    """Meters per pixel of the satellite map at this latitude and zoom (lesson 7):
    circumference * cos(latitude) / 2**zoom / 256"""
    return EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat_deg)) / 2 ** zoom / TILE_PX


def scale_factor(height_m, hfov_deg, width_px, lat_deg, zoom):
    """How much NAVERA must resize the photo so it has the map's meters per pixel:
    photo meters per pixel / map meters per pixel."""
    return meters_per_pixel(height_m, hfov_deg, width_px) / map_meters_per_pixel(lat_deg, zoom)


def best_zoom(height_m, hfov_deg, width_px, lat_deg, zooms=range(13, 20)):
    """The zoom level (from `zooms`) whose map meters per pixel is the closest to the photo's.
    "Closest" means the smallest RATIO difference: compare abs(math.log(map_mpp / photo_mpp)),
    so 2x too big and 2x too small count the same."""
    photo = meters_per_pixel(height_m, hfov_deg, width_px)
    return min(zooms, key=lambda z: abs(math.log(map_meters_per_pixel(lat_deg, z) / photo)))


# ---------------------------------------------------------------- TODO 4
def tilt_shift_m(height_m, tilt_deg):
    """Distance (m) on the ground between the point under the drone and the centre of the
    picture of a camera tilted by tilt_deg from straight down:  h * tan(tilt)"""
    return height_m * math.tan(math.radians(tilt_deg))


def tilted_extent(height_m, fov_deg, tilt_deg):
    """(near_m, far_m): where the two edges of the picture touch the ground, measured from the
    point under the drone, along the tilt direction (negative = behind).
        near = h * tan(tilt - fov/2)      far = h * tan(tilt + fov/2)
    If tilt + fov/2 >= 90 deg, the far edge sees the sky/horizon: far = math.inf."""
    near = height_m * math.tan(math.radians(tilt_deg - fov_deg / 2.0))
    if tilt_deg + fov_deg / 2.0 >= 90.0:
        return near, math.inf
    return near, height_m * math.tan(math.radians(tilt_deg + fov_deg / 2.0))


# ---- you don't need to change anything below this line (but you can read it!) ----
def _show(label, value, unit=""):
    if value is None:
        print(f"  {label:<46} TODO not done yet")
    elif isinstance(value, tuple):
        print(f"  {label:<46} near {value[0]:.1f} m, far {value[1]:.1f} m")
    else:
        print(f"  {label:<46} {value:.3f} {unit}")


if __name__ == "__main__":
    print("Insta360 top lens, straightened view: 1920 px, 111 deg")
    _show("focal length", focal_px(111, 1920), "px")
    for h in (50, 100, 150, 300):
        _show(f"footprint at {h} m", footprint(h, 111), "m")
    _show("meters per pixel at 150 m", meters_per_pixel(150, 111, 1920), "m/px")
    print("\nThis lab's photos: 960 px, 90 deg")
    _show("height when a 12 m pad is 48 px", height_from_object(12, 48, 90, 960), "m")
    print("\nThe map around Sousse (latitude 35.8)")
    for z in (17, 18, 19):
        _show(f"map meters per pixel at zoom {z}", map_meters_per_pixel(35.8, z), "m/px")
    _show("scale for the zoom-17 map at 300 m", scale_factor(300, 111, 1920, 35.8, 17))
    bz = best_zoom(300, 111, 1920, 35.8)
    print(f"  {'best zoom at 300 m':<46} {bz if bz is not None else 'TODO not done yet'}")
    print("\nTilt")
    _show("picture centre shift, 150 m, tilt 10 deg", tilt_shift_m(150, 10), "m")
    _show("near/far edges, 100 m, fov 60, tilt 20", tilted_extent(100, 60, 20))
