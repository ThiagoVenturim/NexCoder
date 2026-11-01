"""Session capture and state management for authenticated flows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from faccoder_capture.models import CaptchaDetectedError, ReadOnlyViolationError, WebCaptureConfig
from faccoder_capture.web.policy import PolicyEnforcer

MUTATING_KEYWORDS = (
    "delete",
    "post",
    "put",
    "patch",
    "update",
    "submit",
    "create",
    "remove",
    "drop",
    "click",
    "fill",
    "type",
    "press",
    "check",
    "uncheck",
    "select_option",
    "drag",
    "dispatch_event",
    "set_input_files",
)


class SessionManager:
    """Manages browser session state (cookies, local storage) for authenticated captures."""

    def __init__(self, config: WebCaptureConfig, policy_enforcer: PolicyEnforcer | None = None) -> None:
        self.config = config
        self.policy = policy_enforcer or PolicyEnforcer(config)

    def load_storage_state(self, path: str | Path) -> dict[str, Any]:
        """Load browser storage_state from JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Session storage state file not found: {path}")

        with open(file_path, encoding="utf-8") as f:
            state: dict[str, Any] = json.load(f)

        return state

    def save_storage_state(self, state: dict[str, Any], path: str | Path) -> None:
        """Save browser storage_state to a local file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        try:
            os.chmod(file_path, 0o600)
        except OSError:
            pass

    def validate_session_page(self, url: str, content: str) -> None:
        """Ensure session page navigation complies with safety policies."""
        self.policy.validate_url(url)
        if self.policy.detect_captcha(content):
            raise CaptchaDetectedError(
                "CAPTCHA challenge detected on session page. CAPTCHA bypass is strictly prohibited."
            )

    def execute_read_only_action(self, action_name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute action only if non-mutating when in read-only mode."""
        is_mutating = any(kw in action_name.lower() for kw in MUTATING_KEYWORDS)
        if self.config.read_only and is_mutating:
            raise ReadOnlyViolationError(
                f"Action '{action_name}' is disallowed in read-only session mode."
            )
        return fn(*args, **kwargs)
