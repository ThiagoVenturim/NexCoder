"""Unit tests for nexcoder_capture.desktop.models."""

from __future__ import annotations

from nexcoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureConfig,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)


def test_bounding_box_dimensions() -> None:
    box = DesktopBoundingBox(left=10, top=20, right=110, bottom=70)
    assert box.width == 100
    assert box.height == 50

    # Inverted or zero coordinates should yield non-negative dimensions
    inverted_box = DesktopBoundingBox(left=100, top=100, right=50, bottom=50)
    assert inverted_box.width == 0
    assert inverted_box.height == 0


def test_window_info_defaults() -> None:
    window = DesktopWindowInfo(
        handle=123456,
        title="Main Application Window",
        class_name="TMainForm",
        process_id=4096,
        bounds=DesktopBoundingBox(left=0, top=0, right=800, bottom=600),
    )
    assert window.handle == 123456
    assert window.title == "Main Application Window"
    assert window.class_name == "TMainForm"
    assert window.process_id == 4096
    assert window.is_visible is True
    assert window.bounds is not None
    assert window.bounds.width == 800


def test_control_node_hierarchy() -> None:
    child = DesktopControlNode(
        handle=1002,
        name="OK",
        control_type="Button",
        class_name="TButton",
        automation_id="btn_ok",
        is_enabled=True,
    )
    parent = DesktopControlNode(
        handle=1001,
        name="Confirmation Dialog",
        control_type="Window",
        class_name="TDialog",
        children=[child],
    )

    assert parent.handle == 1001
    assert len(parent.children) == 1
    assert parent.children[0].name == "OK"
    assert parent.children[0].control_type == "Button"
    assert parent.children[0].automation_id == "btn_ok"


def test_ocr_text_block() -> None:
    bounds = DesktopBoundingBox(left=5, top=10, right=45, bottom=25)
    block = OCRTextBlock(text="Save", bounds=bounds, confidence=0.98)

    assert block.text == "Save"
    assert block.bounds == bounds
    assert block.confidence == 0.98


def test_desktop_capture_config_defaults() -> None:
    config = DesktopCaptureConfig()
    assert config.capture_screenshot is True
    assert config.extract_controls is True
    assert config.run_ocr_fallback is True
    assert config.ocr_min_confidence == 0.5
    assert config.read_only is True
    assert config.max_depth == 20


def test_desktop_capture_result_defaults() -> None:
    result = DesktopCaptureResult()
    assert result.window_info is None
    assert result.controls == []
    assert result.screenshot_bytes is None
    assert result.ocr_results == []
    assert result.metadata == {}
