"""Integrated desktop capture engine with UI Automation and OCR fallback."""

from __future__ import annotations

from faccoder_capture.desktop.engine import (
    MockUIAutomationProvider,
    UIAutomationProvider,
    WindowsUIAutomationProvider,
)
from faccoder_capture.desktop.models import (
    DesktopCaptureConfig,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)
from faccoder_capture.desktop.ocr import MockOCRProvider, OCRProvider, TesseractOCRProvider


class DesktopCaptureEngine:
    """Orchestrates desktop window discovery, control hierarchy extraction, and OCR analysis."""

    def __init__(
        self,
        config: DesktopCaptureConfig | None = None,
        ui_provider: UIAutomationProvider | None = None,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.config = config or DesktopCaptureConfig()

        if ui_provider is not None:
            self.ui_provider = ui_provider
        else:
            win_provider = WindowsUIAutomationProvider()
            self.ui_provider = win_provider if win_provider.is_available() else MockUIAutomationProvider()

        if ocr_provider is not None:
            self.ocr_provider = ocr_provider
        else:
            tess_provider = TesseractOCRProvider()
            self.ocr_provider = tess_provider if tess_provider.is_available() else MockOCRProvider()

    def capture_window(
        self,
        handle: int | None = None,
        title_query: str | None = None,
    ) -> DesktopCaptureResult:
        """Capture a desktop window by handle or title query."""
        window_info = self.ui_provider.find_window(title_query=title_query, handle=handle)
        if not window_info:
            return DesktopCaptureResult(metadata={"error": "Window not found", "query": title_query, "handle": handle})

        target_handle = window_info.handle
        controls: list[DesktopControlNode] = []
        if self.config.extract_controls:
            controls = self.ui_provider.get_window_controls(
                handle=target_handle,
                max_depth=self.config.max_depth,
            )

        screenshot_bytes: bytes | None = None
        if self.config.capture_screenshot:
            screenshot_bytes = self.ui_provider.capture_window_screenshot(target_handle)

        ocr_results: list[OCRTextBlock] = []
        # Run OCR fallback if enabled and screenshot bytes are available
        if self.config.run_ocr_fallback and screenshot_bytes:
            ocr_results = self.ocr_provider.extract_text_blocks(
                image_bytes=screenshot_bytes,
                min_confidence=self.config.ocr_min_confidence,
            )

        return DesktopCaptureResult(
            window_info=window_info,
            controls=controls,
            screenshot_bytes=screenshot_bytes,
            ocr_results=ocr_results,
            metadata={
                "read_only": self.config.read_only,
                "controls_count": len(controls),
                "ocr_count": len(ocr_results),
                "provider": self.ui_provider.__class__.__name__,
                "ocr_provider": self.ocr_provider.__class__.__name__,
            },
        )

    def capture_fixture(
        self,
        window_info: DesktopWindowInfo,
        controls: list[DesktopControlNode] | None = None,
        screenshot_bytes: bytes | None = None,
        ocr_blocks: list[OCRTextBlock] | None = None,
    ) -> DesktopCaptureResult:
        """Deterministic offline capture from in-memory fixture components."""
        mock_ui = MockUIAutomationProvider()
        mock_ui.register_window(
            window=window_info,
            controls=controls,
            screenshot_bytes=screenshot_bytes,
        )
        mock_ocr = MockOCRProvider(predefined_blocks=ocr_blocks)

        engine = DesktopCaptureEngine(
            config=self.config,
            ui_provider=mock_ui,
            ocr_provider=mock_ocr,
        )
        return engine.capture_window(handle=window_info.handle)
