"""OCR text extraction provider and offline fallback for screenshot analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexcoder_capture.desktop.models import DesktopBoundingBox, OCRTextBlock


class OCRProvider(ABC):
    """Abstract interface for extracting text blocks from screenshot images."""

    @abstractmethod
    def extract_text_blocks(
        self,
        image_bytes: bytes,
        min_confidence: float = 0.0,
    ) -> list[OCRTextBlock]:
        """Extract text blocks and their bounding boxes from raw image bytes."""


class MockOCRProvider(OCRProvider):
    """Deterministic offline OCR provider for unit tests and headless environments."""

    def __init__(self, predefined_blocks: list[OCRTextBlock] | None = None) -> None:
        self.predefined_blocks: list[OCRTextBlock] = predefined_blocks or []
        self._signatures: dict[bytes, list[OCRTextBlock]] = {}

    def register_image_blocks(self, image_bytes: bytes, blocks: list[OCRTextBlock]) -> None:
        """Register specific text blocks for matching image bytes."""
        self._signatures[image_bytes] = blocks

    def add_block(
        self,
        text: str,
        left: int = 0,
        top: int = 0,
        right: int = 100,
        bottom: int = 20,
        confidence: float = 1.0,
    ) -> None:
        """Helper to append a mock text block."""
        block = OCRTextBlock(
            text=text,
            bounds=DesktopBoundingBox(left=left, top=top, right=right, bottom=bottom),
            confidence=confidence,
        )
        self.predefined_blocks.append(block)

    def extract_text_blocks(
        self,
        image_bytes: bytes,
        min_confidence: float = 0.0,
    ) -> list[OCRTextBlock]:
        """Return registered or predefined text blocks filtered by min_confidence."""
        candidates = self._signatures.get(image_bytes, self.predefined_blocks)
        return [b for b in candidates if b.confidence >= min_confidence]


class TesseractOCRProvider(OCRProvider):
    """OCR provider wrapping pytesseract when available, with graceful offline handling."""

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self.tesseract_cmd = tesseract_cmd
        self._is_available: bool | None = None

    def is_available(self) -> bool:
        """Check if pytesseract and Pillow are importable and binary configured."""
        if self._is_available is not None:
            return self._is_available
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            self._is_available = True
        except (ImportError, Exception):
            self._is_available = False
        return self._is_available

    def extract_text_blocks(
        self,
        image_bytes: bytes,
        min_confidence: float = 0.0,
    ) -> list[OCRTextBlock]:
        """Perform OCR via pytesseract, returning parsed bounding boxes and confidence."""
        if not self.is_available():
            return []

        import io

        import pytesseract
        from PIL import Image

        try:
            img = Image.open(io.BytesIO(image_bytes))
            data: dict[str, list[Any]] = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
            )

            blocks: list[OCRTextBlock] = []
            num_boxes = len(data.get("text", []))
            for i in range(num_boxes):
                text = str(data["text"][i]).strip()
                if not text:
                    continue

                try:
                    raw_conf = float(data["conf"][i]) if i < len(data["conf"]) else -1.0
                except (ValueError, TypeError):
                    raw_conf = -1.0

                if raw_conf < 0:
                    continue

                conf = max(0.0, min(1.0, raw_conf / 100.0))
                if conf < min_confidence:
                    continue

                try:
                    left = int(data["left"][i])
                    top = int(data["top"][i])
                    width = int(data["width"][i])
                    height = int(data["height"][i])
                except (ValueError, TypeError, KeyError):
                    continue

                blocks.append(
                    OCRTextBlock(
                        text=text,
                        bounds=DesktopBoundingBox(
                            left=left,
                            top=top,
                            right=left + width,
                            bottom=top + height,
                        ),
                        confidence=conf,
                    )
                )
            return blocks
        except Exception:
            return []
