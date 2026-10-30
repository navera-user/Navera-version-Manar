"""Tests of navera_lite/image.py (mission 08). Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_image.py -q
"""
import math

import numpy as np
import pytest

from navera_lite import image


def test_to_uint8_rounds_and_clips_never_wraps():
    out = image.to_uint8(np.array([-3.0, 0.6, 254.6, 300.0, 1000.0]))
    assert out.dtype == np.uint8
    assert out.tolist() == [0, 1, 255, 255, 255]


def test_to_float01_divides_by_the_dtype_maximum():
    assert image.to_float01(np.array([255], np.uint8))[0] == pytest.approx(1.0)
    assert image.to_float01(np.array([65535], np.uint16))[0] == pytest.approx(1.0)
    assert image.to_float01(np.array([0.25])).dtype == np.float32
    with pytest.raises(ValueError):
        image.to_float01(np.array([True, False]))


def test_normalise_stretches_any_dtype_and_survives_a_uniform_image():
    out = image.normalise(np.array([[7000, 7500], [8000, 7250]], np.uint16))
    assert out.dtype == np.uint8 and out.min() == 0 and out.max() == 255
    assert image.normalise(np.full((3, 3), 9.5)).tolist() == [[0] * 3] * 3


def test_convolve2d_flips_the_kernel_and_mirrors_the_border():
    img = np.arange(20.0).reshape(4, 5)
    shift = np.zeros((3, 3))
    shift[1, 0] = 1.0                       # a 1 LEFT of the centre: a true convolution reads img(y, x + 1)
    out = image.convolve2d(img, shift)
    assert out.dtype == np.float32
    assert out[2, 1] == img[2, 2]
    assert out[2, 4] == img[2, 3]           # reflect 101 at the right border


def test_sobel_is_positive_when_brighter_to_the_right():
    gx, gy = image.sobel(np.tile(np.arange(6.0) * 2.0, (6, 1)))
    assert gx[3, 2] == pytest.approx(2.0)
    assert abs(gy[3, 2]) < 1e-6


def test_affine_matrix_keeps_its_centre_and_turns_counter_clockwise_on_screen():
    M = image.affine_matrix(90.0, 1.0, (5.0, 5.0))
    assert M @ np.array([5.0, 5.0, 1.0]) == pytest.approx([5.0, 5.0])
    assert M @ np.array([6.0, 5.0, 1.0]) == pytest.approx([5.0, 4.0])      # right of centre → above it


def test_warp_affine_identity_and_outside_is_zero():
    img = np.arange(12.0).reshape(3, 4)
    same = image.warp_affine(img, np.array([[1.0, 0, 0], [0, 1.0, 0]]), (4, 3))
    assert np.allclose(same, img)
    moved = image.warp_affine(img, np.array([[1.0, 0, 10.0], [0, 1.0, 0]]), (4, 3))
    assert np.all(moved == 0)


def test_like_map_turns_the_photo_north_up():
    p = np.zeros((41, 41), np.uint8)
    p[0:3, 19:22] = 255                     # a mark at the top of the photo
    out = image.like_map(p, 90.0, 1.0, 1.0)  # the top looks east
    assert out.dtype == np.uint8 and out.shape == (58, 58)
    y, x = np.unravel_index(int(out.argmax()), out.shape)
    assert abs(y - 28.5) <= 1 and x > 40
    assert image.like_map(p, 0.0, 0.5, 1.0).shape == (int(round(math.hypot(41, 41) * 0.5)),) * 2
