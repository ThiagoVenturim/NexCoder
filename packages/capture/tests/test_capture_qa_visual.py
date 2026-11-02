"""Unit tests for faccoder_capture.qa.visual."""

from __future__ import annotations

import struct
import sys
import zlib
from unittest.mock import MagicMock, patch

from faccoder_capture.qa.visual import _parse_png_dimensions, compare_screenshots

# Deterministic 1x1 synthetic PNG
PNG_1X1_A = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_solid_png(
    width: int,
    height: int,
    color: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> bytes:
    """Generate valid PNG bytes using standard library only (struct + zlib)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    row_bytes = b"\x00" + bytes(color) * width
    raw_data = row_bytes * height
    idat = _chunk(b"IDAT", zlib.compress(raw_data))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


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


def test_compare_screenshots_pillow_engine_mocked() -> None:
    mock_base = MagicMock()
    mock_base.size = (10, 10)
    mock_base.width = 10
    mock_base.height = 10
    mock_base.convert.return_value = mock_base

    mock_cand = MagicMock()
    mock_cand.size = (10, 10)
    mock_cand.width = 10
    mock_cand.height = 10
    mock_cand.convert.return_value = mock_cand
    mock_cand_copy = MagicMock()
    mock_cand.copy.return_value = mock_cand_copy

    mock_diff = MagicMock()
    mock_diff.getbbox.return_value = (5, 5, 6, 6)
    # 99 identical pixels, 1 differing pixel
    mock_diff.getdata.return_value = [(0, 0, 0, 0)] * 99 + [(255, 0, 0, 255)]

    mock_image = MagicMock()
    mock_image.open.side_effect = [mock_base, mock_cand]

    mock_chops = MagicMock()
    mock_chops.difference.return_value = mock_diff

    mock_draw = MagicMock()

    mock_pil = MagicMock()
    mock_pil.Image = mock_image
    mock_pil.ImageChops = mock_chops
    mock_pil.ImageDraw = mock_draw

    with patch.dict(
        sys.modules,
        {
            "PIL": mock_pil,
            "PIL.Image": mock_image,
            "PIL.ImageChops": mock_chops,
            "PIL.ImageDraw": mock_draw,
        },
    ):
        img_a = _create_solid_png(10, 10, (255, 255, 255, 255))
        img_b = _create_solid_png(10, 10, (255, 255, 255, 255)) + b"extra"

        res_strict = compare_screenshots(img_a, img_b, threshold=0.005)
        assert res_strict.is_match is False
        assert res_strict.diff_score == 0.01
        assert res_strict.mismatched_pixels == 1
        assert res_strict.diff_bounds == [(5, 5, 6, 6)]

        # Reset mock side_effect for next run
        mock_image.open.side_effect = [mock_base, mock_cand]
        res_lenient = compare_screenshots(img_a, img_b, threshold=0.02)
        assert res_lenient.is_match is True
        assert res_lenient.diff_score == 0.01


def test_compare_screenshots_fallback_without_pillow() -> None:
    # Pure Python fallback by ensuring PIL import fails
    with patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
        buf1 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\x1f\x15c4AAAA"
        buf2 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00\x1f\x15c4BBBB"

        res = compare_screenshots(buf1, buf2, threshold=0.05)
        assert res.metadata["engine"] == "fallback_byte_level"
        assert res.diff_score > 0.0
