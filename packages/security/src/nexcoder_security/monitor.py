from __future__ import annotations

import json
import re
from typing import Any, Literal

from nexcoder_control.approval.target_gate import redact_secrets
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_core import PromptInjectionBlockedError
from pydantic import BaseModel, Field

from nexcoder_security.models import Severity


class MonitorViolation(BaseModel):
    """Single rule violation detected by RuntimeSecurityMonitor."""

    rule_id: str
    severity: Severity = Severity.HIGH
    description: str
    remediation: str


class MonitorInspectionResult(BaseModel):
    """Outcome of inspecting a runtime prompt or tool invocation."""

    allowed: bool
    blocked: bool
    target_type: Literal["prompt", "tool_call"]
    sanitized_text: str = ""
    violations: list[MonitorViolation] = Field(default_factory=list)


class RuntimeMonitorConfig(BaseModel):
    """Configuration for the optional runtime security monitor."""

    enabled: bool = True
    block_on_detection: bool = True
    max_prompt_chars: int = Field(default=16000, ge=64)
    require_role_separation: bool = False
    allowed_tools: list[str] | None = None


_PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str], Severity, str, str]] = [
    (
        "runtime.prompt.instruction-override",
        re.compile(
            r"(?i)\b(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)|"
            r"disregard\s+(?:all\s+)?(?:system|previous|prior)\s+(?:prompt|instructions|rules)|"
            r"forget\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
            r"override\s+system\s+(?:prompt|instructions)|system\s+override\s*:)\b"
        ),
        Severity.CRITICAL,
        "Prompt contains instruction-override directive attempting to supersede system rules.",
        "Reject or strip override directives and isolate user text in a structured user message.",
    ),
    (
        "runtime.prompt.role-spoofing",
        re.compile(
            r"(?i)(?:^|\n)\s*(?:system\s*:\s*you\s+are|<\|im_start\|>\s*system|\[system\s+instruction\]|"
            r"###\s*system\s+override|developer\s+mode\s+enabled|you\s+are\s+now\s+in\s+developer\s+mode)"
        ),
        Severity.HIGH,
        "Prompt attempts role-boundary spoofing or control-token injection.",
        "Strip control tokens and role headers from user-supplied text before building messages.",
    ),
    (
        "runtime.prompt.secret-exfiltration-directive",
        re.compile(
            r"(?i)\b(?:print|reveal|output|repeat|exfiltrate|leak|dump)\s+"
            r"(?:the\s+|your\s+|all\s+)?(?:system\s+prompt|hidden\s+instructions|api[_\s]?keys?|secrets?|env\s+vars)\b"
        ),
        Severity.HIGH,
        "Prompt requests exfiltration of system prompt, hidden instructions, or runtime credentials.",
        "Block prompt exfiltration attempts and keep secrets out of LLM context.",
    ),
]

_TOOL_DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str], Severity, str, str]] = [
    (
        "runtime.tool.shell-injection",
        re.compile(r"(?:;\s*(?:rm|cat|curl|wget|bash|sh|powershell|cmd)\b|\|\|\s*(?:sh|bash)\b|`[^`]+`|\$\([^)]+\))"),
        Severity.CRITICAL,
        "Tool arguments contain shell metacharacter command chaining or subshell substitution.",
        "Validate tool arguments against strict schemas and reject shell metacharacters.",
    ),
    (
        "runtime.tool.path-traversal",
        re.compile(r"(?:\.\./|\.\.\\|/etc/passwd|c:\\windows\\system32)", re.IGNORECASE),
        Severity.HIGH,
        "Tool arguments contain path traversal sequence or sensitive OS file reference.",
        "Resolve paths with resolve_inside(base_dir, user_path) and reject traversal patterns.",
    ),
    (
        "runtime.tool.ssrf-internal-target",
        re.compile(
            r"(?i)(?:https?://(?:169\.254\.169\.254|127\.0\.0\.1|localhost|0\.0\.0\.0|metadata\.google\.internal)"
            r"|file:///)"
        ),
        Severity.CRITICAL,
        "Tool arguments reference internal loopback, cloud metadata service, or local file URI (SSRF).",
        "Enforce an explicit outbound HTTPS host allowlist and block metadata/loopback addresses.",
    ),
    (
        "runtime.tool.sql-injection",
        re.compile(
            r"(?i)(?:'\s*OR\s+['\"]?1['\"]?\s*=\s*['\"]?1|;\s*DROP\s+TABLE\b|UNION\s+SELECT\b)",
        ),
        Severity.CRITICAL,
        "Tool arguments contain SQL injection tautology or stacked query payload.",
        "Pass tool parameters as typed bind variables and reject raw SQL fragments.",
    ),
]


class RuntimeSecurityMonitor:
    """Optional runtime monitor that inspects prompts and tool calls and blocks injection patterns."""

    def __init__(
        self,
        config: RuntimeMonitorConfig | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
    ) -> None:
        self.config = config or RuntimeMonitorConfig()
        self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()

    def inspect_prompt(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        external_data: str | None = None,
        actor: str = "runtime",
        raise_on_block: bool | None = None,
    ) -> MonitorInspectionResult:
        """Inspect a prompt and optional external data for prompt injection, size limits, and role separation."""
        if not self.config.enabled:
            return MonitorInspectionResult(
                allowed=True,
                blocked=False,
                target_type="prompt",
                sanitized_text=prompt,
                violations=[],
            )

        violations: list[MonitorViolation] = []
        combined_text = prompt or ""

        # 1. Input length limit check
        if len(combined_text) > self.config.max_prompt_chars:
            violations.append(
                MonitorViolation(
                    rule_id="runtime.prompt.length-exceeded",
                    severity=Severity.MEDIUM,
                    description=(
                        f"Prompt length ({len(combined_text)} chars) exceeds configured maximum "
                        f"({self.config.max_prompt_chars} chars)."
                    ),
                    remediation=f"Truncate or chunk user input to at most {self.config.max_prompt_chars} characters.",
                )
            )

        # 2. Role separation check
        if self.config.require_role_separation and not (system_prompt and system_prompt.strip()):
            violations.append(
                MonitorViolation(
                    rule_id="runtime.prompt.missing-role-separation",
                    severity=Severity.HIGH,
                    description="Prompt submitted without an isolated system_prompt when role separation is required.",
                    remediation="Supply system instructions in system_prompt and untrusted user input separately.",
                )
            )

        # 3. Direct prompt injection patterns
        for rule_id, pattern, sev, desc, fix in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(combined_text):
                violations.append(
                    MonitorViolation(
                        rule_id=rule_id,
                        severity=sev,
                        description=desc,
                        remediation=fix,
                    )
                )

        # 4. External data treated as command / indirect prompt injection
        if external_data:
            for rule_id, pattern, _sev, _desc, _fix in _PROMPT_INJECTION_PATTERNS:
                if pattern.search(external_data):
                    violations.append(
                        MonitorViolation(
                            rule_id="runtime.prompt.external-data-injection",
                            severity=Severity.CRITICAL,
                            description=(
                                f"External data payload contains embedded instruction override matching '{rule_id}'."
                            ),
                            remediation=(
                                "Isolate external data inside <external_data> tags and strip instruction overrides."
                            ),
                        )
                    )
                    break

        sanitized = str(redact_secrets(combined_text[: self.config.max_prompt_chars]))
        for _rule_id, pattern, _sev, _desc, _fix in _PROMPT_INJECTION_PATTERNS:
            sanitized = pattern.sub("[BLOCKED_DIRECTIVE]", sanitized)

        should_block = len(violations) > 0 and self.config.block_on_detection
        primary_rule = violations[0].rule_id if violations else "runtime.prompt.clean"
        reason = violations[0].description if violations else "Prompt passed runtime inspection."

        self.audit_log.record_runtime_monitor_event(
            actor=actor,
            action="inspect_prompt",
            resource="llm.prompt",
            blocked=should_block,
            rule_id=primary_rule,
            reason=reason,
            severity="warning" if should_block else "info",
            details={
                "violation_count": len(violations),
                "rules": [v.rule_id for v in violations],
            },
        )

        do_raise = self.config.block_on_detection if raise_on_block is None else raise_on_block
        if should_block and do_raise:
            raise PromptInjectionBlockedError(
                reason=f"Prompt blocked by RuntimeSecurityMonitor ({primary_rule}): {reason}",
                violations=violations,
            )

        return MonitorInspectionResult(
            allowed=not should_block,
            blocked=should_block,
            target_type="prompt",
            sanitized_text=sanitized,
            violations=violations,
        )

    def inspect_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str,
        *,
        actor: str = "runtime",
        raise_on_block: bool | None = None,
    ) -> MonitorInspectionResult:
        """Inspect a tool call name and arguments for unauthorized tools or injection payloads."""
        if not self.config.enabled:
            return MonitorInspectionResult(
                allowed=True,
                blocked=False,
                target_type="tool_call",
                sanitized_text=str(arguments),
                violations=[],
            )

        violations: list[MonitorViolation] = []
        clean_tool = tool_name.strip()

        # 1. Check allowlist if configured
        if self.config.allowed_tools is not None and clean_tool not in self.config.allowed_tools:
            violations.append(
                MonitorViolation(
                    rule_id="runtime.tool.unauthorized-tool",
                    severity=Severity.HIGH,
                    description=f"Tool '{clean_tool}' is not in the configured allowed_tools list.",
                    remediation="Restrict tool invocations to the explicit allowlist of safe tools.",
                )
            )

        # 2. Check if raw unvalidated string was passed instead of structured dict
        if isinstance(arguments, str):
            raw_args_text = arguments
            violations.append(
                MonitorViolation(
                    rule_id="runtime.tool.unstructured-raw-arguments",
                    severity=Severity.MEDIUM,
                    description=f"Tool '{clean_tool}' invoked with raw unvalidated text instead of a typed schema.",
                    remediation="Parse and validate tool arguments against a strict Pydantic schema before execution.",
                )
            )
        else:
            raw_args_text = json.dumps(arguments, default=str)

        # 3. Check dangerous patterns and prompt injection inside tool arguments
        for rule_id, pattern, sev, desc, fix in _TOOL_DANGEROUS_PATTERNS + _PROMPT_INJECTION_PATTERNS:
            if pattern.search(raw_args_text):
                violations.append(
                    MonitorViolation(
                        rule_id=rule_id,
                        severity=sev,
                        description=f"Tool '{clean_tool}': {desc}",
                        remediation=fix,
                    )
                )

        sanitized = str(redact_secrets(raw_args_text))
        should_block = len(violations) > 0 and self.config.block_on_detection
        primary_rule = violations[0].rule_id if violations else "runtime.tool.clean"
        reason = violations[0].description if violations else f"Tool '{clean_tool}' arguments passed inspection."

        self.audit_log.record_runtime_monitor_event(
            actor=actor,
            action="inspect_tool_call",
            resource=f"tool:{clean_tool}",
            blocked=should_block,
            rule_id=primary_rule,
            reason=reason,
            severity="warning" if should_block else "info",
            details={
                "tool_name": clean_tool,
                "violation_count": len(violations),
                "rules": [v.rule_id for v in violations],
            },
        )

        do_raise = self.config.block_on_detection if raise_on_block is None else raise_on_block
        if should_block and do_raise:
            raise PromptInjectionBlockedError(
                reason=f"Tool call '{clean_tool}' blocked by RuntimeSecurityMonitor ({primary_rule}): {reason}",
                violations=violations,
            )

        return MonitorInspectionResult(
            allowed=not should_block,
            blocked=should_block,
            target_type="tool_call",
            sanitized_text=sanitized,
            violations=violations,
        )
