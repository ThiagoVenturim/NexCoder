"""Policy and safety enforcement for web capture."""

from __future__ import annotations

import re
import urllib.robotparser
from typing import Any
from urllib.parse import urlparse

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_capture.models import (
    CaptchaDetectedError,
    DomainNotAllowedError,
    ReadOnlyViolationError,
    RobotsDisallowedError,
    WebCaptureConfig,
)

CAPTCHA_SIGNATURES: list[re.Pattern[str]] = [
    re.compile(r"recaptcha", re.IGNORECASE),
    re.compile(r"hcaptcha", re.IGNORECASE),
    re.compile(r"cf-turnstile", re.IGNORECASE),
    re.compile(r"cf-challenge", re.IGNORECASE),
    re.compile(r"arkoselabs", re.IGNORECASE),
    re.compile(r"funcaptcha", re.IGNORECASE),
    re.compile(r"g-recaptcha", re.IGNORECASE),
    re.compile(r"challenge-running", re.IGNORECASE),
    re.compile(r"verify you are human", re.IGNORECASE),
    re.compile(r"complete the captcha", re.IGNORECASE),
]


class PolicyEnforcer:
    """Enforces safety, legal, and operational boundaries for web capture."""

    def __init__(
        self,
        config: WebCaptureConfig,
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
    ) -> None:
        self.config = config
        if target_gate is not None:
            self.target_gate = target_gate
            self.audit_log = audit_log if audit_log is not None else target_gate.audit_log
        else:
            self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
            self.target_gate = TargetAuthorizationGate(audit_log=self.audit_log)
        self._robots_parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def verify_target_authorization(
        self,
        url: str,
        *,
        owned_target: bool | None = None,
        authorized_by: str | None = None,
        approval_token: str | None = None,
        mode: str = "web_capture",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Verify target ownership or explicit authorization and record in audit log."""
        effective_owned = owned_target if owned_target is not None else self.config.owned_target
        effective_actor = authorized_by if authorized_by is not None else self.config.authorized_by
        return self.target_gate.verify_target(
            target=url,
            mode=mode,
            owned_target=effective_owned,
            authorized_by=effective_actor,
            approval_token=approval_token,
            metadata=metadata,
        )

    def register_robots_txt(self, base_url: str, robots_content: str) -> None:
        """Register robots.txt content for a given origin/base URL."""
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(robots_content.splitlines())
        self._robots_parsers[origin] = parser

    def validate_url(self, url: str) -> None:
        """Validate URL against allowed domains and robots.txt."""
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https", "file"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        if parsed.scheme == "file":
            # Local file fixtures are always allowed
            return

        hostname = (parsed.hostname or "").lower()
        if self.config.allowed_domains:
            matched = any(
                hostname == allowed.lower()
                or hostname.endswith("." + allowed.lower())
                or parsed.netloc.lower() == allowed.lower()
                for allowed in self.config.allowed_domains
            )
            if not matched:
                raise DomainNotAllowedError(
                    f"Domain '{parsed.netloc}' is not in allowed domains: {self.config.allowed_domains}"
                )

        if self.config.honor_robots_txt:
            origin = f"{parsed.scheme}://{parsed.netloc}"
            parser = self._robots_parsers.get(origin)
            if parser and not parser.can_fetch(self.config.user_agent, url):
                raise RobotsDisallowedError(
                    f"Fetching URL '{url}' is disallowed by robots.txt for user-agent '{self.config.user_agent}'"
                )

    def detect_captcha(self, content: str) -> bool:
        """Scan content for CAPTCHA challenges."""
        for pattern in CAPTCHA_SIGNATURES:
            if pattern.search(content):
                return True
        return False

    def assert_no_captcha(self, content: str) -> None:
        """Raise CaptchaDetectedError if any CAPTCHA challenge is found."""
        if self.detect_captcha(content):
            raise CaptchaDetectedError("CAPTCHA challenge detected. Bypassing CAPTCHAs is strictly prohibited.")

    def validate_action(self, action_name: str, is_mutating: bool) -> None:
        """Validate that action respects read-only mode."""
        if self.config.read_only and is_mutating:
            raise ReadOnlyViolationError(f"Action '{action_name}' is a mutating action, prohibited in read-only mode.")
