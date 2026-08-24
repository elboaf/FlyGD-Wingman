"""The premultiply step is pure and gets real tests; the ULW call is a
thin wrapper around it and is covered by the smoke checklist.

ULW_ALPHA requires PREMULTIPLIED BGRA. Getting this wrong makes
translucent pixels glow -- which looks correct on a dark background and
wrong everywhere else, so it is exactly the bug that ships.
"""
from PIL import Image

from obs_youtube_uploader.preview import layered


def test_opaque_pixel_is_bgra_ordered():
    img = Image.new("RGBA", (1, 1), (10, 20, 30, 255))
    assert layered.to_premultiplied_bgra(img) == bytes([30, 20, 10, 255])


def test_half_alpha_is_premultiplied():
    img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    b, g, r, a = layered.to_premultiplied_bgra(img)
    assert a == 128
    assert (b, g, r) == (50 * 128 // 255, 100 * 128 // 255, 200 * 128 // 255)


def test_transparent_pixel_is_fully_zeroed():
    """A transparent pixel that keeps its colour shows as a coloured halo
    around the preview's rounded corners."""
    img = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    assert layered.to_premultiplied_bgra(img) == bytes([0, 0, 0, 0])


def test_length_is_four_bytes_per_pixel():
    img = Image.new("RGBA", (7, 5), (1, 2, 3, 4))
    assert len(layered.to_premultiplied_bgra(img)) == 7 * 5 * 4


def test_non_rgba_input_is_converted():
    """chrome.render always returns RGBA, but a caller passing RGB should
    not produce three-byte pixels and a misaligned DIB."""
    img = Image.new("RGB", (2, 2), (10, 20, 30))
    assert len(layered.to_premultiplied_bgra(img)) == 2 * 2 * 4
