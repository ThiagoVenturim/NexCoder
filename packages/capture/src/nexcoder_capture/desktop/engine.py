"""UI Automation reader for desktop screens (VCL, WinForms, WPF)."""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from typing import Any

from nexcoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopControlNode,
    DesktopWindowInfo,
)

logger = logging.getLogger(__name__)

# 1x1 transparent PNG bytes for offline synthetic screenshot generation
OFFLINE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class UIAutomationProvider(ABC):
    """Abstract provider interface for inspecting desktop windows and controls."""

    @abstractmethod
    def list_windows(self) -> list[DesktopWindowInfo]:
        """List open desktop application windows."""

    @abstractmethod
    def find_window(
        self,
        title_query: str | None = None,
        handle: int | None = None,
    ) -> DesktopWindowInfo | None:
        """Find a target window by exact handle or case-insensitive title query."""

    @abstractmethod
    def get_window_controls(
        self,
        handle: int,
        max_depth: int = 20,
    ) -> list[DesktopControlNode]:
        """Extract the UI control hierarchy for a window (strictly read-only)."""

    @abstractmethod
    def capture_window_screenshot(self, handle: int) -> bytes | None:
        """Capture screenshot image bytes of the window area."""


class MockUIAutomationProvider(UIAutomationProvider):
    """Deterministic offline provider for testing and headless CI environments."""

    def __init__(self) -> None:
        self.windows: dict[int, DesktopWindowInfo] = {}
        self.controls: dict[int, list[DesktopControlNode]] = {}
        self.screenshots: dict[int, bytes] = {}

    def register_window(
        self,
        window: DesktopWindowInfo,
        controls: list[DesktopControlNode] | None = None,
        screenshot_bytes: bytes | None = None,
    ) -> None:
        """Register a mock window with optional control tree and screenshot."""
        self.windows[window.handle] = window
        self.controls[window.handle] = controls or []
        self.screenshots[window.handle] = screenshot_bytes or OFFLINE_PNG_BYTES

    def list_windows(self) -> list[DesktopWindowInfo]:
        return list(self.windows.values())

    def find_window(
        self,
        title_query: str | None = None,
        handle: int | None = None,
    ) -> DesktopWindowInfo | None:
        if handle is not None:
            return self.windows.get(handle)
        if title_query is not None:
            query_lower = title_query.lower()
            for w in self.windows.values():
                if query_lower in w.title.lower():
                    return w
        return None

    def get_window_controls(
        self,
        handle: int,
        max_depth: int = 20,
    ) -> list[DesktopControlNode]:
        return self.controls.get(handle, [])

    def capture_window_screenshot(self, handle: int) -> bytes | None:
        return self.screenshots.get(handle, OFFLINE_PNG_BYTES)


class WindowsUIAutomationProvider(UIAutomationProvider):
    """Windows UI Automation provider using pywinauto / win32 APIs (strictly read-only)."""

    def __init__(self) -> None:
        self._is_windows = sys.platform == "win32"

    def is_available(self) -> bool:
        """Check if running on Windows with necessary runtime libraries available."""
        if not self._is_windows:
            return False
        try:
            import pywinauto  # noqa: F401

            return True
        except ImportError:
            return False

    def list_windows(self) -> list[DesktopWindowInfo]:
        """Enumerate top-level desktop windows using pywinauto or Win32."""
        if not self.is_available():
            return []

        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            windows: list[DesktopWindowInfo] = []
            for w in desktop.windows():
                try:
                    wrapper = w.wrapper_object()
                    handle = wrapper.handle
                    title = wrapper.window_text()
                    class_name = wrapper.class_name()
                    rect = wrapper.rectangle()
                    bounds = DesktopBoundingBox(
                        left=rect.left,
                        top=rect.top,
                        right=rect.right,
                        bottom=rect.bottom,
                    )
                    windows.append(
                        DesktopWindowInfo(
                            handle=handle,
                            title=title,
                            class_name=class_name,
                            bounds=bounds,
                            is_visible=wrapper.is_visible(),
                        )
                    )
                except Exception as exc:
                    logger.debug("Skipping window due to inspection error: %s", exc)
                    continue
            return windows
        except Exception as exc:
            logger.debug("Failed listing windows: %s", exc)
            return []

    def find_window(
        self,
        title_query: str | None = None,
        handle: int | None = None,
    ) -> DesktopWindowInfo | None:
        windows = self.list_windows()
        if handle is not None:
            for w in windows:
                if w.handle == handle:
                    return w
            return None
        if title_query is not None:
            q = title_query.lower()
            for w in windows:
                if q in w.title.lower():
                    return w
        return None

    def get_window_controls(
        self,
        handle: int,
        max_depth: int = 20,
    ) -> list[DesktopControlNode]:
        """Read control hierarchy recursively (inspection only, zero mutation)."""
        if not self.is_available():
            return []

        try:
            from pywinauto import Application

            app = Application(backend="uia").connect(handle=handle)
            window = app.window(handle=handle)
            root_wrapper = window.wrapper_object()

            def _traverse(wrapper: Any, depth: int) -> DesktopControlNode:
                bounds: DesktopBoundingBox | None = None
                try:
                    rect = wrapper.rectangle()
                    bounds = DesktopBoundingBox(
                        left=rect.left,
                        top=rect.top,
                        right=rect.right,
                        bottom=rect.bottom,
                    )
                except Exception as exc:
                    logger.debug("Failed getting rectangle for control: %s", exc)

                try:
                    raw_name = wrapper.window_text()
                    name = str(raw_name) if isinstance(raw_name, str) else ""
                except Exception:
                    name = ""

                try:
                    raw_type = getattr(wrapper.element_info, "control_type", None)
                    control_type = str(raw_type) if isinstance(raw_type, str) and raw_type else "Control"
                except Exception:
                    control_type = "Control"

                try:
                    raw_class = wrapper.class_name()
                    class_name = str(raw_class) if isinstance(raw_class, str) else ""
                except Exception:
                    class_name = ""

                try:
                    is_enabled = bool(wrapper.is_enabled())
                except Exception:
                    is_enabled = True

                try:
                    is_visible = bool(wrapper.is_visible())
                except Exception:
                    is_visible = True

                try:
                    raw_id = getattr(wrapper.element_info, "automation_id", None)
                    automation_id = str(raw_id) if isinstance(raw_id, str) and raw_id else None
                except Exception:
                    automation_id = None

                children: list[DesktopControlNode] = []
                if depth < max_depth:
                    try:
                        for child in wrapper.children():
                            children.append(_traverse(child, depth + 1))
                    except Exception as exc:
                        logger.debug("Failed traversing child controls: %s", exc)

                try:
                    raw_handle = getattr(wrapper, "handle", 0)
                    handle_val = int(raw_handle) if isinstance(raw_handle, int) else 0
                except Exception:
                    handle_val = 0

                return DesktopControlNode(
                    handle=handle_val,
                    name=name,
                    control_type=control_type,
                    class_name=class_name,
                    bounds=bounds,
                    is_enabled=is_enabled,
                    is_visible=is_visible,
                    automation_id=automation_id,
                    children=children,
                )

            return [_traverse(root_wrapper, depth=0)]
        except Exception as exc:
            logger.debug("Failed getting window controls for handle %s: %s", handle, exc)
            return []

    def capture_window_screenshot(self, handle: int) -> bytes | None:
        """Capture screenshot bytes via window wrapper."""
        if not self.is_available():
            return None

        import io

        try:
            from pywinauto import Application

            app = Application(backend="uia").connect(handle=handle)
            window = app.window(handle=handle)
            img = window.capture_as_image()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None
