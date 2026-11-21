"""Unit tests for nexcoder_capture.desktop.ocr."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from nexcoder_capture.desktop.models import DesktopBoundingBox, OCRTextBlock
from nexcoder_capture.desktop.ocr import MockOCRProvider, TesseractOCRProvider


def test_mock_ocr_provider_add_block_and_confidence_filter() -> None:
    provider = MockOCRProvider()
    provider.add_block(text="Low Conf", left=0, top=0, right=50, bottom=20, confidence=0.3)
    provider.add_block(text="High Conf", left=0, top=30, right=50, bottom=50, confidence=0.9)

    # All blocks with min_confidence = 0.0
    all_blocks = provider.extract_text_blocks(b"dummy-image", min_confidence=0.0)
    assert len(all_blocks) == 2

    # Filtered by min_confidence = 0.5
    high_blocks = provider.extract_text_blocks(b"dummy-image", min_confidence=0.5)
    assert len(high_blocks) == 1
    assert high_blocks[0].text == "High Conf"


def test_mock_ocr_provider_register_image_blocks() -> None:
    provider = MockOCRProvider()
    custom_block = OCRTextBlock(
        text="Special Title",
        bounds=DesktopBoundingBox(left=10, top=10, right=100, bottom=30),
        confidence=1.0,
    )
    provider.register_image_blocks(b"image-signature-a", [custom_block])

    # For image signature A
    blocks_a = provider.extract_text_blocks(b"image-signature-a")
    assert len(blocks_a) == 1
    assert blocks_a[0].text == "Special Title"

    # For other images, falls back to predefined_blocks (empty)
    blocks_other = provider.extract_text_blocks(b"other-image")
    assert blocks_other == []


def test_tesseract_provider_fallback_when_unavailable() -> None:
    provider = TesseractOCRProvider()
    with patch.object(provider, "is_available", return_value=False):
        assert provider.extract_text_blocks(b"image-bytes") == []


def test_tesseract_provider_is_available_import_failure() -> None:
    provider = TesseractOCRProvider()
    with patch.dict(sys.modules, {"pytesseract": None}):
        provider._is_available = None
        assert provider.is_available() is False


def test_tesseract_provider_with_mocked_pytesseract() -> None:
    provider = TesseractOCRProvider(tesseract_cmd="/usr/bin/tesseract")

    mock_pytesseract = MagicMock()
    mock_pytesseract.Output.DICT = "dict"
    mock_pytesseract.image_to_data.return_value = {
        "text": ["", "  ", "Confirm", "Cancel", "Blurry"],
        "conf": ["-1", "50", "95", "88", "20"],
        "left": [0, 0, 10, 80, 150],
        "top": [0, 0, 20, 20, 20],
        "width": [0, 0, 60, 50, 40],
        "height": [0, 0, 25, 25, 25],
    }

    mock_pil = MagicMock()
    mock_pil.Image.open.return_value = MagicMock()

    with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_pil.Image}):
        with patch.object(provider, "is_available", return_value=True):
            blocks = provider.extract_text_blocks(b"mock-png-data", min_confidence=0.5)

            # Only "Confirm" (95% -> 0.95) and "Cancel" (88% -> 0.88) should be extracted
            assert len(blocks) == 2
            assert blocks[0].text == "Confirm"
            assert blocks[0].confidence == 0.95
            assert blocks[0].bounds is not None
            assert blocks[0].bounds.left == 10
            assert blocks[0].bounds.width == 60

            assert blocks[1].text == "Cancel"
            assert blocks[1].confidence == 0.88


def test_tesseract_provider_exception_handling() -> None:
    provider = TesseractOCRProvider()
    mock_pytesseract = MagicMock()
    mock_pytesseract.image_to_data.side_effect = RuntimeError("Tesseract crash")

    mock_pil = MagicMock()

    with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil}):
        with patch.object(provider, "is_available", return_value=True):
            assert provider.extract_text_blocks(b"invalid-image") == []


def test_tesseract_provider_non_numeric_confidence() -> None:
    provider = TesseractOCRProvider()
    mock_pytesseract = MagicMock()
    mock_pytesseract.Output.DICT = "dict"
    mock_pytesseract.image_to_data.return_value = {
        "text": ["StructureRow", "ValidWord"],
        "conf": ["", "92"],
        "left": [0, 10],
        "top": [0, 20],
        "width": [50, 40],
        "height": [20, 15],
    }
    mock_pil = MagicMock()
    mock_pil.Image.open.return_value = MagicMock()

    with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "PIL": mock_pil, "PIL.Image": mock_pil.Image}):
        with patch.object(provider, "is_available", return_value=True):
            blocks = provider.extract_text_blocks(b"dummy-image")
            assert len(blocks) == 1
            assert blocks[0].text == "ValidWord"
            assert blocks[0].confidence == 0.92
