"""Unit tests for faccoder_capture.qa.visual."""

from __future__ import annotations

import io
from unittest.mock import patch

from faccoder_capture.qa.visual import _parse_png_dimensions, compare_screenshots
from PIL import Image

# Deterministic 1x1 synthetic PNG
PNG_1X1_A = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_solid_png(width: int, height: int, color: tuple[int, int, int, int]) -> bytes:
    img = Image.new("RGBA", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_parse_png_dimensions() -> None:
    dims = _parse_png_dimensions(PNG_1X1_A)
    assert dims == (1, 1)

    assert _parse_png_dimensions(b"not-a-png-file") is None
    assert _parse_png_dimensions(b"\x89PNG\r\n\x1a\nshort") is None


def test_compare_screenshots_exact_match() -> None:
    res = compare_screenshots(PNG_1X1_A, PNG_1X1_A)
    assert res.is_match is True
    assert res.diff_score == 0.0
    assert res.mismatched_pixels == 0
    assert res.diff_bounds == []


def test_compare_screenshots_dimension_mismatch() -> None:
    img_10x10 = _create_solid_png(10, 10, (255, 255, 255, 255))
    img_20x20 = _create_solid_png(20, 20, (255, 255, 255, 255))

    res = compare_screenshots(img_10x10, img_20x20)
    assert res.is_match is False
    assert res.diff_score == 1.0
    assert res.mismatched_pixels == 400
    assert "Dimension mismatch" in res.metadata.get("error", "")


def test_compare_screenshots_differing_pixels() -> None:
    img_white = _create_solid_png(10, 10, (255, 255, 255, 255))

    # Create candidate with 1 differing pixel out of 100 pixels (1% diff)
    candidate = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
    candidate.putpixel((5, 5), (0, 0, 0, 255))
    buf = io.BytesIO()
    candidate.save(buf, format="PNG")
    img_diff = buf.getvalue()

    # With threshold 0.005 (0.5%), 1% should fail match
    res_strict = compare_screenshots(img_white, img_diff, threshold=0.005)
    assert res_strict.is_match is False
    assert res_strict.diff_score == 0.01
    assert res_strict.mismatched_pixels == 1
    assert len(res_strict.diff_bounds) == 1
    assert res_strict.diff_image_bytes is not None

    # With threshold 0.02 (2%), 1% should pass match
    res_lenient = compare_screenshots(img_white, img_diff, threshold=0.02)
    assert res_lenient.is_match is True
    assert res_lenient.diff_score == 0.01


def test_compare_screenshots_fallback_without_pillow() -> None:
    # Trigger pure Python fallback by forcing exception on PIL import
    with patch("PIL.Image.open", side_effect=ImportError("No Pillow")):
        buf1 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\x1f\x15c4AAAA"
        buf2 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\x1f\x15c4BBBB"

        res = compare_screenshots(buf1, buf2, threshold=0.05)
        assert res.metadata["engine"] == "fallback_byte_level"
        assert res.diff_score > 0.0
