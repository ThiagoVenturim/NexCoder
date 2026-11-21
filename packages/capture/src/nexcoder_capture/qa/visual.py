"""Visual regression comparator for baseline and candidate screenshots."""

from __future__ import annotations

import io
import logging
import struct

from nexcoder_capture.qa.models import VisualDiffResult

logger = logging.getLogger(__name__)


def _parse_png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Parse width and height from PNG IHDR chunk without third-party dependencies."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            width, height = struct.unpack(">II", data[16:24])
            return width, height
        except Exception:
            return None
    return None


def compare_screenshots(
    baseline_bytes: bytes,
    candidate_bytes: bytes,
    threshold: float = 0.01,
) -> VisualDiffResult:
    """Compare baseline and candidate screenshot buffers with configurable mismatch threshold.

    Operates 100% offline. Uses Pillow when available, with a pure Python fallback
    when native image manipulation libraries are absent.
    """
    if baseline_bytes == candidate_bytes:
        dim = _parse_png_dimensions(baseline_bytes)
        total_px = (dim[0] * dim[1]) if dim else 10000
        return VisualDiffResult(
            diff_score=0.0,
            is_match=True,
            threshold=threshold,
            total_pixels=total_px,
            mismatched_pixels=0,
            diff_bounds=[],
            diff_image_bytes=None,
            metadata={"status": "exact_match", "dimensions": dim},
        )

    # Try PIL comparison if installed
    try:
        from PIL import Image, ImageChops, ImageDraw

        baseline_img = Image.open(io.BytesIO(baseline_bytes)).convert("RGBA")
        candidate_img = Image.open(io.BytesIO(candidate_bytes)).convert("RGBA")

        # Check dimension mismatch
        if baseline_img.size != candidate_img.size:
            max_w = max(baseline_img.width, candidate_img.width)
            max_h = max(baseline_img.height, candidate_img.height)
            total_px = max_w * max_h
            return VisualDiffResult(
                diff_score=1.0,
                is_match=False,
                threshold=threshold,
                total_pixels=total_px,
                mismatched_pixels=total_px,
                diff_bounds=[(0, 0, max_w, max_h)],
                diff_image_bytes=None,
                metadata={
                    "error": "Dimension mismatch",
                    "baseline_size": baseline_img.size,
                    "candidate_size": candidate_img.size,
                },
            )

        diff = ImageChops.difference(baseline_img.convert("RGB"), candidate_img.convert("RGB"))
        bbox = diff.getbbox()

        total_pixels = baseline_img.width * baseline_img.height
        if not bbox:
            return VisualDiffResult(
                diff_score=0.0,
                is_match=True,
                threshold=threshold,
                total_pixels=total_pixels,
                mismatched_pixels=0,
                diff_bounds=[],
            )

        # Count differing pixels
        diff_data = diff.getdata()
        mismatched_pixels = 0
        for px in diff_data:
            if any(c > 0 for c in px):
                mismatched_pixels += 1

        diff_score = mismatched_pixels / max(1, total_pixels)
        diff_bounds = [bbox]

        # Generate highlight diff image
        highlight = candidate_img.copy()
        draw = ImageDraw.Draw(highlight)
        draw.rectangle(bbox, outline=(255, 0, 0, 255), width=2)
        out_buf = io.BytesIO()
        highlight.save(out_buf, format="PNG")
        diff_image_bytes = out_buf.getvalue()

        return VisualDiffResult(
            diff_score=diff_score,
            is_match=(diff_score <= threshold),
            threshold=threshold,
            total_pixels=total_pixels,
            mismatched_pixels=mismatched_pixels,
            diff_bounds=diff_bounds,
            diff_image_bytes=diff_image_bytes,
            metadata={"engine": "pillow", "bbox": bbox},
        )
    except Exception as exc:
        logger.debug("Pillow comparison failed, falling back to byte comparison: %s", exc)
        # Pure Python fallback for environments without Pillow
        dim_base = _parse_png_dimensions(baseline_bytes)
        dim_cand = _parse_png_dimensions(candidate_bytes)

        if dim_base and dim_cand and dim_base != dim_cand:
            return VisualDiffResult(
                diff_score=1.0,
                is_match=False,
                threshold=threshold,
                total_pixels=max(dim_base[0] * dim_base[1], dim_cand[0] * dim_cand[1]),
                mismatched_pixels=max(dim_base[0] * dim_base[1], dim_cand[0] * dim_cand[1]),
                diff_bounds=[(0, 0, max(dim_base[0], dim_cand[0]), max(dim_base[1], dim_cand[1]))],
                diff_image_bytes=None,
                metadata={"error": "Dimension mismatch", "fallback": True},
            )

        # Byte-level diff ratio
        max_len = max(len(baseline_bytes), len(candidate_bytes))
        min_len = min(len(baseline_bytes), len(candidate_bytes))
        differing_bytes = abs(len(baseline_bytes) - len(candidate_bytes))

        for b1, b2 in zip(baseline_bytes[:min_len], candidate_bytes[:min_len], strict=False):
            if b1 != b2:
                differing_bytes += 1

        diff_score = differing_bytes / max(1, max_len)
        total_pixels = (dim_base[0] * dim_base[1]) if dim_base else max_len

        return VisualDiffResult(
            diff_score=diff_score,
            is_match=(diff_score <= threshold),
            threshold=threshold,
            total_pixels=total_pixels,
            mismatched_pixels=int(diff_score * total_pixels),
            diff_bounds=[(0, 0, dim_base[0], dim_base[1])] if dim_base else [],
            diff_image_bytes=None,
            metadata={"engine": "fallback_byte_level", "differing_bytes": differing_bytes},
        )
