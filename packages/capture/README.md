# nexcoder-capture

Web and desktop capture, stable selectors extraction, test generation, and QA checks for nexcoder.

## Features

- **Web capture (Playwright)**:
  - Full DOM snapshot, accessibility tree extraction, screenshot capture, HAR network recording.
  - Heuristic extraction of robust, stable selectors (ID, test IDs, ARIA roles, semantics).
  - Session capture for authenticated user flows with strict read-only guarantees, robots.txt compliance, and anti-captcha safety (no bypass attempts).
- **Desktop capture**:
  - Windows UI Automation integration for native desktop applications.
  - OCR screenshot fallback for un-instrumented controls.
- **Test and Page Object generation**:
  - Automatic Playwright Python/TypeScript test and Page Object scaffolding from captured DOM.
- **QA and Accessibility**:
  - Automated visual regression diffing and axe-core accessibility compliance checks.
- **100% Offline-capable**:
  - Designed with deterministic local HTML fixture and mock capture drivers so all tests execute offline without internet access.

## Origin

Ported and generalized for the nexcoder open-source platform, distilling testing patterns and screen
capture mechanisms from earlier enterprise platforms into a vendor-neutral, offline-capable package.

## Installation

```bash
pip install nexcoder-capture
# With Playwright web support:
pip install nexcoder-capture[web]
# With desktop UI automation support:
pip install nexcoder-capture[desktop]
```

## Quick Start

```python
from nexcoder_capture.web import WebCaptureEngine, WebCaptureConfig

engine = WebCaptureEngine(config=WebCaptureConfig(capture_har=True, capture_screenshot=True))
# Capture from local fixture or URL
result = engine.capture_html(
    "<html><body><button id='submit-btn'>Submit</button></body></html>", base_url="https://example.com"
)

print("DOM length:", len(result.dom))
print("Selectors found:", len(result.selectors))
```
