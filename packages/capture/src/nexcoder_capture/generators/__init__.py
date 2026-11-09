"""Automatic test and Page Object generators for Playwright."""

from nexcoder_capture.generators.page_objects import generate_page_object
from nexcoder_capture.generators.playwright import generate_playwright_test

__all__ = [
    "generate_page_object",
    "generate_playwright_test",
]
