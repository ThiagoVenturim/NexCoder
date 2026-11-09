"""Unit tests for nexcoder_capture.desktop.capture."""

from __future__ import annotations

from unittest.mock import patch

from nexcoder_capture.desktop.capture import DesktopCaptureEngine
from nexcoder_capture.desktop.engine import MockUIAutomationProvider
from nexcoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureConfig,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)
from nexcoder_capture.desktop.ocr import MockOCRProvider


def test_desktop_capture_engine_default_providers() -> None:
    # When native Windows or Tesseract are unavailable, engine falls back to Mock providers
    with (
        patch("nexcoder_capture.desktop.capture.WindowsUIAutomationProvider.is_available", return_value=False),
        patch("nexcoder_capture.desktop.capture.TesseractOCRProvider.is_available", return_value=False),
    ):
        engine = DesktopCaptureEngine()
        assert isinstance(engine.ui_provider, MockUIAutomationProvider)
        assert isinstance(engine.ocr_provider, MockOCRProvider)


def test_capture_window_not_found() -> None:
    ui_provider = MockUIAutomationProvider()
    engine = DesktopCaptureEngine(ui_provider=ui_provider)

    result = engine.capture_window(title_query="NonExistentWindow")
    assert result.window_info is None
    assert result.metadata.get("error") == "Window not found"


def test_capture_window_success_flow() -> None:
    ui_provider = MockUIAutomationProvider()
    ocr_provider = MockOCRProvider()

    window_info = DesktopWindowInfo(
        handle=2001,
        title="Account Ledger",
        class_name="TAccountForm",
        bounds=DesktopBoundingBox(left=0, top=0, right=800, bottom=600),
    )
    control1 = DesktopControlNode(handle=3001, name="Post", control_type="Button")
    control2 = DesktopControlNode(handle=3002, name="Amount", control_type="Edit")

    ocr_provider.add_block(text="Post Entry", left=10, top=10, right=100, bottom=30, confidence=0.95)
    ocr_provider.add_block(text="Low Noise", left=0, top=0, right=10, bottom=10, confidence=0.2)

    ui_provider.register_window(
        window=window_info,
        controls=[control1, control2],
        screenshot_bytes=b"sample-screenshot-bytes",
    )

    config = DesktopCaptureConfig(
        capture_screenshot=True,
        extract_controls=True,
        run_ocr_fallback=True,
        ocr_min_confidence=0.5,
        read_only=True,
    )

    engine = DesktopCaptureEngine(
        config=config,
        ui_provider=ui_provider,
        ocr_provider=ocr_provider,
    )

    result = engine.capture_window(handle=2001)

    assert result.window_info is not None
    assert result.window_info.handle == 2001
    assert result.window_info.title == "Account Ledger"

    # Controls extracted
    assert len(result.controls) == 2
    assert result.controls[0].name == "Post"

    # Screenshot captured
    assert result.screenshot_bytes == b"sample-screenshot-bytes"

    # OCR filtered by min_confidence=0.5
    assert len(result.ocr_results) == 1
    assert result.ocr_results[0].text == "Post Entry"

    # Metadata verified
    assert result.metadata["read_only"] is True
    assert result.metadata["controls_count"] == 2
    assert result.metadata["ocr_count"] == 1


def test_capture_window_with_features_disabled() -> None:
    ui_provider = MockUIAutomationProvider()
    ocr_provider = MockOCRProvider()

    window_info = DesktopWindowInfo(handle=5001, title="Test Window")
    ui_provider.register_window(
        window=window_info,
        controls=[DesktopControlNode(name="Test")],
        screenshot_bytes=b"screenshot-bytes",
    )
    ocr_provider.add_block("Some Text", confidence=0.9)

    config = DesktopCaptureConfig(
        capture_screenshot=False,
        extract_controls=False,
        run_ocr_fallback=False,
    )
    engine = DesktopCaptureEngine(
        config=config,
        ui_provider=ui_provider,
        ocr_provider=ocr_provider,
    )

    result = engine.capture_window(handle=5001)

    assert result.window_info is not None
    assert result.controls == []
    assert result.screenshot_bytes is None
    assert result.ocr_results == []


def test_capture_fixture_offline() -> None:
    engine = DesktopCaptureEngine()

    window_info = DesktopWindowInfo(
        handle=9001,
        title="Fixture Test Dialog",
        class_name="TDialog",
        bounds=DesktopBoundingBox(left=50, top=50, right=450, bottom=350),
    )
    control = DesktopControlNode(handle=9002, name="Cancel", control_type="Button")
    ocr_block = OCRTextBlock(
        text="Cancel",
        bounds=DesktopBoundingBox(left=60, top=300, right=140, bottom=330),
        confidence=0.99,
    )

    result = engine.capture_fixture(
        window_info=window_info,
        controls=[control],
        screenshot_bytes=b"fake-fixture-png",
        ocr_blocks=[ocr_block],
    )

    assert result.window_info is not None
    assert result.window_info.handle == 9001
    assert len(result.controls) == 1
    assert result.controls[0].name == "Cancel"
    assert result.screenshot_bytes == b"fake-fixture-png"
    assert len(result.ocr_results) == 1
    assert result.ocr_results[0].text == "Cancel"
