"""Unit tests for faccoder_capture.web.session."""

from __future__ import annotations

from pathlib import Path

import pytest
from faccoder_capture.models import CaptchaDetectedError, ReadOnlyViolationError, WebCaptureConfig
from faccoder_capture.web.session import SessionManager


def test_storage_state_save_and_load(tmp_path: Path) -> None:
    config = WebCaptureConfig()
    manager = SessionManager(config)

    state_file = tmp_path / "session_state.json"
    dummy_state = {
        "cookies": [{"name": "auth_token", "value": "xyz123", "domain": "example.com"}],
        "origins": [],
    }

    manager.save_storage_state(dummy_state, state_file)
    assert state_file.exists()

    loaded = manager.load_storage_state(state_file)
    assert loaded == dummy_state


def test_storage_state_file_not_found(tmp_path: Path) -> None:
    manager = SessionManager(WebCaptureConfig())
    missing = tmp_path / "non_existent.json"
    with pytest.raises(FileNotFoundError):
        manager.load_storage_state(missing)


def test_validate_session_page_clean() -> None:
    manager = SessionManager(WebCaptureConfig(allowed_domains=["example.com"]))
    manager.validate_session_page("https://example.com/dashboard", "<html><body>Dashboard</body></html>")


def test_validate_session_page_with_captcha() -> None:
    manager = SessionManager(WebCaptureConfig())
    captcha_content = '<html><body><div id="cf-challenge">Verifying</div></body></html>'
    with pytest.raises(CaptchaDetectedError):
        manager.validate_session_page("https://example.com/login", captcha_content)


def test_execute_read_only_action() -> None:
    manager_ro = SessionManager(WebCaptureConfig(read_only=True))

    called = False

    def dummy_func(val: int) -> int:
        nonlocal called
        called = True
        return val * 2

    # Safe read-only action
    res = manager_ro.execute_read_only_action("read_table", dummy_func, 5)
    assert res == 10
    assert called is True

    # Mutating actions prohibited in read-only mode
    for mutating_action in ("submit_form", "delete_item", "post_message", "update_profile", "remove_user"):
        with pytest.raises(ReadOnlyViolationError):
            manager_ro.execute_read_only_action(mutating_action, dummy_func, 1)

    # In read-write mode, mutating actions are permitted
    manager_rw = SessionManager(WebCaptureConfig(read_only=False))
    res2 = manager_rw.execute_read_only_action("submit_form", dummy_func, 7)
    assert res2 == 14
