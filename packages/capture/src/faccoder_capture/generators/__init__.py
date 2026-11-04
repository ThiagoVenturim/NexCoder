"""Automatic test and Page Object generators for Playwright."""

from faccoder_capture.generators.page_objects import generate_page_object
from faccoder_capture.generators.playwright import generate_playwright_test

__all__ = [
    "generate_page_object",
    "generate_playwright_test",
]
