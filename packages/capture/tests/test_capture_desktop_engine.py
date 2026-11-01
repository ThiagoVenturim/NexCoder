"""Unit tests for faccoder_capture.desktop.engine."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from faccoder_capture.desktop.engine import (
    OFFLINE_PNG_BYTES,
    MockUIAutomationProvider,
    WindowsUIAutomationProvider,
)
from faccoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopControlNode,
    DesktopWindowInfo,
)


def test_mock_ui_automation_provider_window_management() -> None:
    provider = MockUIAutomationProvider()

    win1 = DesktopWindowInfo(
        handle=1001,
        title="Settings - App",
        class_name="TConfigForm",
        bounds=DesktopBoundingBox(left=0, top=0, right=600, bottom=400),
    )
    win2 = DesktopWindowInfo(
        handle=1002,
        title="Order Entry",
        class_name="TOrderForm",
        bounds=DesktopBoundingBox(left=100, top=100, right=900, bottom=700),
    )

    control1 = DesktopControlNode(handle=2001, name="Save", control_type="Button")
    provider.register_window(win1, controls=[control1], screenshot_bytes=b"fake-bytes")
    provider.register_window(win2)

    # list_windows
    all_windows = provider.list_windows()
    assert len(all_windows) == 2

    # find_window by handle
    found_by_handle = provider.find_window(handle=1001)
    assert found_by_handle is not None
    assert found_by_handle.title == "Settings - App"

    # find_window by title substring (case-insensitive)
    found_by_title = provider.find_window(title_query="order")
    assert found_by_title is not None
    assert found_by_title.handle == 1002

    # find_window not found
    assert provider.find_window(title_query="nonexistent") is None
    assert provider.find_window(handle=9999) is None

    # get_window_controls
    controls = provider.get_window_controls(handle=1001)
    assert len(controls) == 1
    assert controls[0].name == "Save"

    # get_window_controls for empty window
    assert provider.get_window_controls(handle=1002) == []

    # capture_window_screenshot
    assert provider.capture_window_screenshot(1001) == b"fake-bytes"
    # fallback to default OFFLINE_PNG_BYTES
    assert provider.capture_window_screenshot(1002) == OFFLINE_PNG_BYTES


def test_windows_provider_graceful_fallback_when_unavailable() -> None:
    provider = WindowsUIAutomationProvider()

    with patch.object(provider, "is_available", return_value=False):
        assert provider.list_windows() == []
        assert provider.find_window(handle=100) is None
        assert provider.find_window(title_query="test") is None
        assert provider.get_window_controls(handle=100) == []
        assert provider.capture_window_screenshot(handle=100) is None


def test_windows_provider_is_available_non_windows() -> None:
    provider = WindowsUIAutomationProvider()
    provider._is_windows = False
    assert provider.is_available() is False


def test_windows_provider_with_mocked_pywinauto() -> None:
    provider = WindowsUIAutomationProvider()

    # Mock window wrapper
    mock_wrapper = MagicMock()
    mock_wrapper.handle = 1234
    mock_wrapper.window_text.return_value = "Main Window"
    mock_wrapper.class_name.return_value = "TMainForm"
    mock_wrapper.is_visible.return_value = True

    mock_rect = MagicMock()
    mock_rect.left = 10
    mock_rect.top = 20
    mock_rect.right = 810
    mock_rect.bottom = 620
    mock_wrapper.rectangle.return_value = mock_rect

    mock_child_wrapper = MagicMock()
    mock_child_wrapper.handle = 5678
    mock_child_wrapper.window_text.return_value = "Submit"
    mock_child_wrapper.class_name.return_value = "TButton"
    mock_child_wrapper.is_visible.return_value = True
    mock_child_wrapper.is_enabled.return_value = True
    mock_child_wrapper.element_info.control_type = "Button"
    mock_child_wrapper.element_info.automation_id = "btn_submit"
    mock_child_wrapper.rectangle.return_value = mock_rect
    mock_child_wrapper.children.return_value = []

    mock_wrapper.children.return_value = [mock_child_wrapper]
    mock_wrapper.element_info.control_type = "Window"
    mock_wrapper.element_info.automation_id = "main_window"

    mock_win_obj = MagicMock()
    mock_win_obj.wrapper_object.return_value = mock_wrapper

    mock_desktop = MagicMock()
    mock_desktop.windows.return_value = [mock_win_obj]

    mock_app = MagicMock()
    mock_app.window.return_value = mock_win_obj

    # Create mock pywinauto module
    mock_pywinauto = MagicMock()
    mock_pywinauto.Desktop.return_value = mock_desktop
    mock_pywinauto.Application.return_value.connect.return_value = mock_app

    with patch.dict(sys.modules, {"pywinauto": mock_pywinauto}):
        with patch.object(provider, "is_available", return_value=True):
            # Test list_windows
            windows = provider.list_windows()
            assert len(windows) == 1
            assert windows[0].handle == 1234
            assert windows[0].title == "Main Window"
            assert windows[0].bounds.width == 800

            # Test find_window
            found = provider.find_window(title_query="main")
            assert found is not None
            assert found.handle == 1234

            # Test get_window_controls with traversal
            controls = provider.get_window_controls(handle=1234, max_depth=5)
            assert len(controls) == 1
            root_control = controls[0]
            assert root_control.handle == 1234
            assert root_control.control_type == "Window"
            assert len(root_control.children) == 1
            assert root_control.children[0].handle == 5678
            assert root_control.children[0].name == "Submit"


def test_windows_provider_capture_screenshot_mocked() -> None:
    provider = WindowsUIAutomationProvider()

    mock_img = MagicMock()

    def _fake_save(buf, format):
        buf.write(b"fake-window-png")

    mock_img.save.side_effect = _fake_save

    mock_win = MagicMock()
    mock_win.capture_as_image.return_value = mock_img

    mock_app = MagicMock()
    mock_app.window.return_value = mock_win

    mock_pywinauto = MagicMock()
    mock_pywinauto.Application.return_value.connect.return_value = mock_app

    with patch.dict(sys.modules, {"pywinauto": mock_pywinauto}):
        with patch.object(provider, "is_available", return_value=True):
            screenshot = provider.capture_window_screenshot(handle=1234)
            assert screenshot == b"fake-window-png"
