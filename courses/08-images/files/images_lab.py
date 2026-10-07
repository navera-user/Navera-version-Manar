# Lab 8 — Digital images: dtypes, histograms, convolution and affine warps
#
# Fill in the functions marked TODO, save (Ctrl+S), then run:
#     python3 demo.py
# An image is a numpy array: img[row, column] = img[y, x]. A colour image has shape (height, width, 3)
# with the channels in OpenCV's order BLUE, GREEN, RED; a grey image has shape (height, width).
# Stored pictures are uint8 (whole numbers 0..255). COMPUTE in float32, STORE / DISPLAY in uint8:
# every function says which dtype it returns — respect it, the checks verify it.

import cv2
import numpy as np


def flip_horizontal(img):
    """Mirror image (left <-> right). EXAMPLE — already done: one slice reverses the columns."""
    return img[:, ::-1].copy()


def to_uint8(a):
    """Any array of numbers -> uint8 picture: round to the nearest integer, clip to 0..255, convert."""
    # TODO 1: np.rint, np.clip(..., 0, 255), .astype(np.uint8)  (the ORDER matters: clip before astype)
    return None


def to_gray(img):
    """Grey uint8 (H, W) from a BGR uint8 image with Y = 0.299 R + 0.587 G + 0.114 B.
    A picture that is already grey (2 dimensions) is returned unchanged."""
    # TODO 2: split the channels (img[..., 0] is BLUE), compute in float32, then to_uint8()
    return None


def histogram(gray):
    """Array of 256 counts: h[v] = number of pixels with value v (grey uint8 picture)."""
    # TODO 3: np.bincount(gray.ravel(), minlength=256)
    return None


def normalise(gray):
    """Min-max stretch: darkest pixel -> 0, brightest -> 255. Returns uint8.
    A uniform picture (max == min) is returned unchanged."""
    # TODO 4: (g - min) / (max - min) * 255 in float32, then to_uint8()   (forgetting it gives float64!)
    return None


def equalise(gray):
    """Histogram equalisation of a grey uint8 picture (the same result as cv2.equalizeHist, ± 1).
    A uniform picture (one grey value) is returned unchanged, as a uint8 copy: there N == cdf_min,
    and the formula would divide 0 by 0."""
    # TODO 5: cdf = cumulative sum of histogram(); cdf_min = first non-zero value of cdf;
    #         if N == cdf_min (uniform picture): return gray.copy()
    #         lut = to_uint8((cdf - cdf_min) / (N - cdf_min) * 255) with N = number of pixels; return lut[gray]
    return None


def convolve2d(img, kernel):
    """True 2-D convolution (the kernel is flipped), same size as img, border 'reflect 101'
    (OpenCV's default: ...c b | a b c ... ). Returns float32. Kernel sizes are odd."""
    # TODO 6: pad with np.pad(..., mode="reflect"); flip the kernel (kernel[::-1, ::-1]);
    #         out = sum over (i, j) of flipped[i, j] * padded[i : i + H, j : j + W]
    return None


def gaussian_kernel(k, sigma):
    """k x k Gaussian kernel (float32, sum = 1). If sigma <= 0, use OpenCV's rule
    sigma = 0.3 * ((k - 1) * 0.5 - 1) + 0.8."""
    # TODO 7: x = np.arange(k) - (k - 1) / 2; g = exp(-x² / (2 sigma²)); normalise; np.outer(g, g)
    return None


def sobel(gray):
    """(gx, gy): float32 derivatives along x (positive when it gets brighter to the RIGHT) and y
    (positive when it gets brighter DOWNWARDS), equal to cv2.Sobel(gray, cv2.CV_32F, 1, 0) and (0, 1)."""
    # TODO 8: two 3 x 3 Sobel kernels and your convolve2d(). Mind the flip of a true convolution!
    return None


def rotation_scale_matrix(cx, cy, angle_deg, scale):
    """2 x 3 affine matrix (float64) that turns by angle_deg COUNTER-CLOCKWISE on screen and scales by
    `scale`, around the point (cx, cy). Must equal cv2.getRotationMatrix2D((cx, cy), angle_deg, scale)."""
    # TODO 9: a = s cos θ, b = s sin θ; [[a, b, (1 - a) cx - b cy], [-b, a, b cx + (1 - a) cy]]
    return None


def warp_affine(gray, M, out_w, out_h):
    """Apply the 2 x 3 affine M (source -> destination) to a grey picture with BILINEAR interpolation,
    by INVERSE mapping; pixels that come from outside the source are 0. Returns float32 (out_h, out_w)."""
    # TODO 10: invert A = M[:, :2] (np.linalg.inv) to get, for every destination pixel (u, v), its
    #          source (x, y) = A⁻¹ ((u, v) - t); then bilinear: x0 = floor(x), fx = x - x0 (same for y),
    #          blend the 4 neighbours read with _get(gray, ys, xs), which gives 0 outside the picture.
    return None


def make_like_map(photo, heading_deg, photo_m_per_px, map_m_per_px, method="normalise"):
    """Prepare a drone photo for comparison with the north-up map: grey, contrast (method =
    "normalise", "equalise" or "clahe"), then ONE affine warp that turns north up and brings the photo
    to the map's meters per pixel. Output size: round(w * s) x round(h * s). Returns uint8.

    heading_deg: direction of the photo's TOP, in degrees clockwise from north (like a bearing)."""
    # TODO 11: to_gray -> contrast -> s = ? -> M = rotation_scale_matrix(w/2, h/2, ?, s) -> shift M so the
    #          photo centre lands at the output centre -> warp_affine -> back to uint8
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----

def _get(gray, ys, xs):
    """Pixel values gray[ys, xs] as float32 for integer index arrays; 0 where (ys, xs) is outside."""
    h, w = gray.shape
    inside = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
    vals = gray[np.clip(ys, 0, h - 1), np.clip(xs, 0, w - 1)].astype(np.float32)
    return np.where(inside, vals, np.float32(0.0))


def difference(a, b):
    """Mean absolute difference of two grey pictures of the same size: 0 = identical, 255 = opposite."""
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def similarity(a, b):
    """Correlation of two grey pictures of the same size: 1 = same pattern, 0 = unrelated."""
    a = a.astype(np.float32).ravel()
    b = b.astype(np.float32).ravel()
    a, b = a - a.mean(), b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


def middle(img, size=160):
    """The size x size block in the middle of a picture."""
    h, w = img.shape[:2]
    return img[(h - size) // 2:(h - size) // 2 + size, (w - size) // 2:(w - size) // 2 + size]
