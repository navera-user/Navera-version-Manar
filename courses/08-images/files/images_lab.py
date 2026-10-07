# Lab 8 — Images are just numbers
#
# Fill in the functions marked TODO, save (Ctrl+S), then run:
#     python3 demo.py
# An image is a numpy array: img[row, column] = img[y, x]. A colour image has shape
# (height, width, 3) with the channels in OpenCV's order BLUE, GREEN, RED; a grey image has shape
# (height, width). Pixel values are whole numbers from 0 (black) to 255 (white): dtype uint8.

import cv2
import numpy as np


def flip_horizontal(img):
    """Mirror image (left <-> right). EXAMPLE — already done: one slice reverses the columns."""
    return img[:, ::-1].copy()


def to_gray(img):
    """Grey version (2-D array, uint8) of a BGR colour image. A grey image is returned unchanged."""
    # TODO 1: if the image has 2 dimensions it is already grey; otherwise use cv2.cvtColor(..., cv2.COLOR_BGR2GRAY)
    return None


def crop(img, x, y, w, h):
    """The rectangle of w x h pixels whose top-left corner is column x, row y."""
    # TODO 2: one slice — rows first, then columns
    return None


def crop_center(img, w, h):
    """The w x h rectangle in the middle of the image."""
    # TODO 3: compute the top-left corner, then call crop()
    return None


def rotate(img, angle_deg):
    """Turn the picture COUNTER-CLOCKWISE by angle_deg around its centre; same size (corners are cut)."""
    # TODO 4: cv2.getRotationMatrix2D(centre, angle, 1.0), then cv2.warpAffine(img, M, (width, height))
    return None


def scale(img, factor):
    """Resize by `factor` (0.5 = half the width and half the height)."""
    # TODO 5: new size = (round(width * factor), round(height * factor)) — careful, cv2.resize wants (WIDTH, HEIGHT)
    return None


def adjust(img, contrast, brightness):
    """new pixel = old pixel x contrast + brightness, kept between 0 and 255, as uint8."""
    # TODO 6: compute in float (img.astype(np.float32)), np.clip to 0..255, back to np.uint8
    return None


def normalise(img):
    """Stretch the values so the darkest pixel becomes 0 and the brightest 255 (uint8).
    An image where all pixels are equal is returned unchanged."""
    # TODO 7: (img - min) / (max - min) x 255
    return None


def blur(img, k):
    """Gaussian blur with a k x k window (k odd: 3, 5, 7...)."""
    # TODO 8: cv2.GaussianBlur with the window (k, k) and sigma 0 (OpenCV chooses it from k)
    return None


def edges(img, low=50, high=150):
    """Edge map (uint8, 0 or 255) of the picture: grey, blurred with a 5 x 5 window, then Canny."""
    # TODO 9: to_gray -> blur(..., 5) -> cv2.Canny(..., low, high)
    return None


def make_like_map(photo, heading_deg, photo_m_per_px, map_m_per_px):
    """Prepare a drone photo to be compared with the map: grey, normalised, north up, map scale.

    heading_deg: direction of the photo's TOP, in degrees clockwise from north (like a bearing).
    """
    # TODO 10: to_gray -> normalise -> rotate (which way? see the course) -> scale (which factor?)
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----

def difference(a, b):
    """Mean absolute difference of two grey pictures of the same size: 0 = identical, 255 = opposite."""
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def similarity(a, b):
    """Correlation of two grey pictures of the same size: 1 = same pattern, 0 = unrelated."""
    a = a.astype(np.float32).ravel() - a.mean()
    b = b.astype(np.float32).ravel() - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0
