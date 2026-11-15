from __future__ import annotations

import ast
import contextlib
import re
import time
from pathlib import Path
from typing import Any

from nexcoder_control.approval.target_gate import redact_secrets

from nexcoder_security.models import (
    Finding,
    FindingCategory,
    Location,
    Remediation,
    ScanResult,
    Severity,
)
from nexcoder_security.scanners.base import BaseScanner

_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache"}
_TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".yaml", ".yml", ".json", ".sql", ".md", ".txt", ".har"}


def _iter_source_files(target: Path, extensions: set[str] | None = None) -> list[Path]:
    """Return deterministic list of source files under target."""
    allowed = extensions or _TEXT_EXTENSIONS
    if target.is_file():
        return [target]
    if not target.exists():
        return []
    files = [
        p
        for p in sorted(target.rglob("*"))
        if p.is_file() and not any(part in _IGNORE_DIRS for part in p.parts) and p.suffix.lower() in allowed
    ]
    return files


def _safe_snippet(line: str) -> str:
    """Return a trimmed, secret-redacted snippet for responsible disclosure."""
    cleaned = str(redact_secrets(line.strip()))
    if len(cleaned) > 160:
        return cleaned[:157] + "..."
    return cleaned


class PromptInjectionScanner(BaseScanner):
    """Scanner for prompt injection vulnerabilities, missing system/user separation, and unvalidated tool calls."""

    def __init__(self) -> None:
        super().__init__(executable_name="prompt-injection", name="prompt-injection")

    def is_available(self) -> bool:
        return True

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> ScanResult:
        start_time = time.perf_counter()
        target = Path(target_path)
        findings: list[Finding] = []

        rules: list[tuple[str, re.Pattern[str], str, str, Severity, list[str], str, str]] = [
            (
                "prompt-injection.unsanitized-llm-input",
                re.compile(
                    r"(?:(?:llm|model|client|chat_model|agent)\s*\.\s*"
                    r"(?:invoke|generate|complete|chat|predict|run|ask)|"
                    r"completions\.create|call_llm|ask_llm)\s*\([^)]*"
                    r"(?:f[\"'][^\"']*\{[^}]*(?:user_input|user_prompt|raw_input|untrusted|query|user_text|message)"
                    r"[^}]*\}|"
                    r"[\+]\s*(?:user_input|user_prompt|raw_input|untrusted|query|user_text)|"
                    r"\.format\s*\([^)]*(?:user_input|user_prompt|raw_input|untrusted))"
                ),
                "Unsanitized user input passed directly to LLM prompt",
                (
                    "User-controlled input reaches the LLM call via direct interpolation or concatenation "
                    "without length bounds, delimiter isolation, or sanitization."
                ),
                Severity.HIGH,
                ["CWE-77", "CWE-74"],
                (
                    "Enforce length limits, sanitize untrusted text, place user input in a dedicated 'user' role "
                    "message with XML/structural delimiters, and optionally wrap the call with RuntimeSecurityMonitor."
                ),
                (
                    "sanitized = monitor.inspect_prompt(user_input, system_prompt=SYSTEM_PROMPT)\n"
                    'messages = [{"role": "system", "content": SYSTEM_PROMPT}, '
                    '{"role": "user", "content": sanitized.sanitized_text}]'
                ),
            ),
            (
                "prompt-injection.unsanitized-prompt-concat",
                re.compile(
                    r"(?:prompt|system_prompt|full_prompt|llm_prompt)\s*=\s*"
                    r"(?:f[\"'][^\"']*\{[^}]*(?:user_input|user_prompt|raw_input|untrusted|user_message|user_query)"
                    r"[^}]*\}|"
                    r"[^#\n]*[\+]\s*(?:user_input|user_prompt|raw_input|untrusted|user_message|user_query))"
                ),
                "Prompt constructed by concatenating or interpolating raw user input",
                (
                    "Building a prompt string by directly concatenating or formatting raw user input allows "
                    "adversarial instructions to override system behavior."
                ),
                Severity.HIGH,
                ["CWE-77", "CWE-1427"],
                (
                    "Separate system instructions from user input using structured message roles and "
                    "validate/bound user input with RuntimeSecurityMonitor before sending to the model."
                ),
                (
                    'messages = [{"role": "system", "content": system_instructions}, '
                    '{"role": "user", "content": user_input[:MAX_LEN]}]'
                ),
            ),
            (
                "prompt-injection.external-data-as-command",
                re.compile(
                    r"(?:system_prompt|instructions|prompt|command_prompt)\s*=\s*"
                    r"(?:f[\"'][^\"']*\{[^}]*(?:external_doc|external_data|web_content|scraped_text|"
                    r"rag_chunk|webhook_body|email_body|untrusted_doc|external_text)[^}]*\}|"
                    r"[^#\n]*[\+]\s*(?:external_doc|external_data|web_content|scraped_text|"
                    r"rag_chunk|webhook_body|email_body|untrusted_doc|external_text))"
                ),
                "External data interpolated into prompt instructions as executable command context",
                (
                    "Untrusted external content (documents, web pages, webhooks, or emails) is embedded directly "
                    "into instruction context, enabling indirect prompt injection."
                ),
                Severity.CRITICAL,
                ["CWE-1427", "CWE-74"],
                (
                    "Treat external data strictly as untrusted passive data inside isolated data tags "
                    "(e.g., <external_data>...</external_data>) and strip imperative override directives."
                ),
                'user_msg = f"<external_data>{sanitize_external(external_doc)}</external_data>"',
            ),
            (
                "prompt-injection.missing-role-separation",
                re.compile(
                    r"[\"'][^\"']*System\s*:\s*[^\"']*User\s*:\s*\{?[^\"']*[\"']|"
                    r"(?:system_prompt|system_instructions)\s*\+\s*(?:[\"']\\n[\"']\s*\+\s*)?"
                    r"(?:user_input|user_prompt|user_message)"
                ),
                "Missing separation between system instructions and user input",
                (
                    "System instructions and user input are merged into a single flat text block rather than "
                    "isolated system and user message roles."
                ),
                Severity.HIGH,
                ["CWE-1427"],
                (
                    "Pass system instructions in a dedicated system role message and untrusted user input in a "
                    "separate user role message."
                ),
                'messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}]',
            ),
            (
                "prompt-injection.unvalidated-tool-call",
                re.compile(
                    r"(?:call_tool|run_tool|execute_tool|invoke_tool|dispatch_tool|tool_runner)\s*\(\s*"
                    r"(?:llm_output|raw_tool_args|external_text|user_input|untrusted_args|raw_response)"
                ),
                "Tool invoked directly with unvalidated external or LLM text",
                (
                    "A tool or function is invoked with raw text from an external source or unvalidated LLM output "
                    "without schema validation or tool allowlisting."
                ),
                Severity.CRITICAL,
                ["CWE-20", "CWE-77"],
                (
                    "Validate tool names against an explicit allowlist, parse arguments against a strict Pydantic "
                    "schema, and inspect calls with RuntimeSecurityMonitor.inspect_tool_call()."
                ),
                (
                    "monitor.inspect_tool_call(tool_name, validated_args.model_dump())\n"
                    "result = execute_tool(tool_name, validated_args)"
                ),
            ),
            (
                "prompt-injection.embedded-override-pattern",
                re.compile(
                    r"(?i)\b(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
                    r"disregard\s+(?:all\s+)?(?:system|previous)\s+(?:prompt|instructions|rules)|"
                    r"system\s+override\s*:|you\s+are\s+now\s+in\s+developer\s+mode)\b"
                ),
                "Embedded prompt injection override directive detected",
                (
                    "File contains an explicit instruction-override or jailbreak phrase designed to hijack "
                    "LLM system instructions."
                ),
                Severity.HIGH,
                ["CWE-1427"],
                (
                    "Remove adversarial override directives from prompts/inputs and block them at runtime "
                    "using RuntimeSecurityMonitor."
                ),
                "# Reject or strip adversarial instruction override patterns before model invocation",
            ),
        ]

        for file_path in _iter_source_files(target):
            with contextlib.suppress(Exception):
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    for rule_id, pattern, title, desc, sev, cwes, fix_summary, fixed_code in rules:
                        if pattern.search(line):
                            snippet = _safe_snippet(line)
                            diff = (
                                f"--- a/{file_path}\n+++ b/{file_path}\n"
                                f"@@ -{line_idx},1 +{line_idx},1 @@\n-{snippet}\n+{fixed_code}\n"
                            )
                            findings.append(
                                Finding(
                                    id=f"prompt-injection-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=rule_id,
                                    title=title,
                                    description=f"{desc} ({file_path}:{line_idx})",
                                    severity=sev,
                                    category=FindingCategory.PROMPT_INJECTION,
                                    location=Location(
                                        file_path=str(file_path),
                                        line_start=line_idx,
                                        line_end=line_idx,
                                        snippet=snippet,
                                    ),
                                    cwe_ids=cwes,
                                    remediation=Remediation(
                                        summary=fix_summary,
                                        diff_patch=diff,
                                        references=["https://owasp.org/www-project-top-10-for-large-language-model-applications/"],
                                    ),
                                    raw_data={"rule_id": rule_id, "line": line_idx},
                                )
                            )

        return self._create_result(target, findings, start_time, version="1.0.0-native", is_fallback=False)


class SQLInjectionScanner(BaseScanner):
    """Scanner for SQL injection vulnerabilities via string concatenation, formatting, or unsafe ORM usage."""

    def __init__(self) -> None:
        super().__init__(executable_name="sql-injection", name="sql-injection")

    def is_available(self) -> bool:
        return True

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> ScanResult:
        start_time = time.perf_counter()
        target = Path(target_path)
        findings: list[Finding] = []

        sql_keywords = r"(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE)"
        rules: list[tuple[str, re.Pattern[str], str, str, Severity, str, str]] = [
            (
                "sql-injection.concatenated-query",
                re.compile(
                    rf"(?i)(?:f[\"'][^\n]*{sql_keywords}[^\n]*\{{\s*[^}}]+\s*\}}|"
                    rf"[\"'][^\n]*{sql_keywords}[^\n]*[\"']\s*(?:\+|\.format\s*\(|%\s*\(?))"
                ),
                "SQL query constructed via string concatenation or interpolation",
                (
                    "SQL statement is dynamically assembled using string concatenation, f-strings, .format(), "
                    "or % formatting instead of parameterized bind variables."
                ),
                Severity.CRITICAL,
                (
                    "Use parameterized queries with bind placeholders (e.g., '?' or ':param') "
                    "and pass values as a tuple/dict."
                ),
                'cursor.execute("SELECT * FROM users WHERE username = ?", (username,))',
            ),
            (
                "sql-injection.unsafe-orm-raw",
                re.compile(
                    r"(?:\.(?:raw|extra)\s*\(\s*(?:f[\"']|[^)]*\+|[^)]*\.format\()|"
                    r"\b(?:text|RawSQL)\s*\(\s*(?:f[\"']|[^)]*\+|[^)]*\.format\()|"
                    r"\.(?:execute|executemany|query)\s*\(\s*(?:f[\"']|[^)]*\+|[^)]*\.format\())"
                ),
                "Unsafe raw SQL or ORM query execution with interpolated parameters",
                (
                    "ORM or database session executes raw SQL built with dynamic string interpolation, "
                    "bypassing ORM parameterization safeguards."
                ),
                Severity.HIGH,
                (
                    "Pass bind parameters separately to session.execute(text('... WHERE id = :id'), {'id': val}) "
                    "or use ORM filters."
                ),
                'session.execute(text("SELECT * FROM accounts WHERE id = :id"), {"id": account_id})',
            ),
        ]

        for file_path in _iter_source_files(target, {".py", ".js", ".ts", ".sql"}):
            with contextlib.suppress(Exception):
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    for rule_id, pattern, title, desc, sev, fix_summary, fixed_code in rules:
                        if pattern.search(line):
                            snippet = _safe_snippet(line)
                            diff = (
                                f"--- a/{file_path}\n+++ b/{file_path}\n"
                                f"@@ -{line_idx},1 +{line_idx},1 @@\n-{snippet}\n+{fixed_code}\n"
                            )
                            findings.append(
                                Finding(
                                    id=f"sql-injection-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=rule_id,
                                    title=title,
                                    description=f"{desc} ({file_path}:{line_idx})",
                                    severity=sev,
                                    category=FindingCategory.SQL_INJECTION,
                                    location=Location(
                                        file_path=str(file_path),
                                        line_start=line_idx,
                                        line_end=line_idx,
                                        snippet=snippet,
                                    ),
                                    cwe_ids=["CWE-89"],
                                    remediation=Remediation(
                                        summary=fix_summary,
                                        diff_patch=diff,
                                        references=["https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"],
                                    ),
                                    raw_data={"rule_id": rule_id, "line": line_idx},
                                )
                            )

        return self._create_result(target, findings, start_time, version="1.0.0-native", is_fallback=False)


class DataLeakageScanner(BaseScanner):
    """Scanner for secret/token/PII leakage in logs, responses, reports, HAR files, state dumps, and egress."""

    def __init__(self) -> None:
        super().__init__(executable_name="data-leakage", name="data-leakage")

    def is_available(self) -> bool:
        return True

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> ScanResult:
        start_time = time.perf_counter()
        target = Path(target_path)
        findings: list[Finding] = []

        sensitive_vars = (
            r"(?:api_key|apikey|secret|token|access_token|refresh_token|auth_token|bearer_token|"
            r"password|passwd|private_key|client_secret|cpf|ssn|credit_card|authorization)"
        )

        rules: list[tuple[str, re.Pattern[str], str, str, Severity, list[str], str, str]] = [
            (
                "data-leakage.secret-or-token-in-log",
                re.compile(
                    rf"(?i)(?:logger|logging|log)\s*\.\s*(?:debug|info|warning|warn|error|critical|exception)\s*"
                    rf"\([^)]*\b{sensitive_vars}\b|"
                    rf"\bprint\s*\(\s*f[\"'][^\n]*\b{sensitive_vars}\b"
                ),
                "Secret, token, or PII written to application logs",
                (
                    "Sensitive credentials, authentication tokens, or personal identifiable information (PII) "
                    "are logged directly to stdout or log sinks."
                ),
                Severity.HIGH,
                ["CWE-532", "CWE-200"],
                (
                    "Redact or mask tokens, secrets, and PII before logging (e.g., use redact_secrets() or log only "
                    "non-sensitive correlation IDs)."
                ),
                'logger.info("Authenticated request processed for user_id=%s", user_id)',
            ),
            (
                "data-leakage.secret-in-response-or-state",
                re.compile(
                    r"(?i)(?:return\s*\{[^}]*[\"'](?:password|passwd|secret|private_key|raw_token|"
                    r"api_key|client_secret|ssn|cpf|credit_card)[\"']\s*:|"
                    r"(?:json\.dumps|pickle\.dumps|har_export|write_report|save_state)\s*\([^)]*"
                    r"\b(?:password|secret|auth_token|api_key|private_key|raw_headers|authorization)\b)"
                ),
                "Sensitive secret, token, or PII exposed in response, report, HAR, or serialized state",
                (
                    "Sensitive credentials, tokens, or PII are included in an API response payload, report, "
                    "HAR capture, or serialized state without redaction."
                ),
                Severity.HIGH,
                ["CWE-200", "CWE-359"],
                (
                    "Strip or redact sensitive fields (passwords, tokens, API keys, Cookie/Authorization headers, PII) "
                    "from response DTOs, HAR exports, reports, and serialized state."
                ),
                "return redact_secrets(response_payload)",
            ),
            (
                "data-leakage.unconfigured-customer-data-egress",
                re.compile(
                    r"(?i)(?:requests|httpx)\s*\.\s*(?:post|put)\s*\([^)]*"
                    r"\b(?:customer_data|client_data|user_pii|tenant_data|patient_data|customer_records)\b"
                ),
                "Customer or PII data sent to external endpoint without explicit egress configuration",
                (
                    "Customer records or PII leave the application boundary via an outbound HTTP call without "
                    "verifying explicit tenant opt-in or data-egress policy."
                ),
                Severity.HIGH,
                ["CWE-359", "CWE-200"],
                (
                    "Gate any outbound transmission of customer data behind an explicit, auditable configuration "
                    "flag (e.g., if config.allow_external_data_egress:) and anonymize PII prior to egress."
                ),
                "if config.allow_external_data_egress:\n    send_anonymized_payload(anonymize(customer_data))",
            ),
        ]

        for file_path in _iter_source_files(target):
            with contextlib.suppress(Exception):
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    for rule_id, pattern, title, desc, sev, cwes, fix_summary, fixed_code in rules:
                        if pattern.search(line):
                            snippet = _safe_snippet(line)
                            diff = (
                                f"--- a/{file_path}\n+++ b/{file_path}\n"
                                f"@@ -{line_idx},1 +{line_idx},1 @@\n-{snippet}\n+{fixed_code}\n"
                            )
                            findings.append(
                                Finding(
                                    id=f"data-leakage-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=rule_id,
                                    title=title,
                                    description=f"{desc} ({file_path}:{line_idx})",
                                    severity=sev,
                                    category=FindingCategory.DATA_LEAKAGE,
                                    location=Location(
                                        file_path=str(file_path),
                                        line_start=line_idx,
                                        line_end=line_idx,
                                        snippet=snippet,
                                    ),
                                    cwe_ids=cwes,
                                    remediation=Remediation(
                                        summary=fix_summary,
                                        diff_patch=diff,
                                    ),
                                    raw_data={"rule_id": rule_id, "line": line_idx},
                                )
                            )

        return self._create_result(target, findings, start_time, version="1.0.0-native", is_fallback=False)


class GeneralSecurityScanner(BaseScanner):
    """Scanner for missing route auth, fail-open auth, CORS wildcard with credentials, timing-unsafe token comparison,
    path traversal, SSRF, and shell injection.
    """

    def __init__(self) -> None:
        super().__init__(executable_name="general-security", name="general-security")

    def is_available(self) -> bool:
        return True

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> ScanResult:
        start_time = time.perf_counter()
        target = Path(target_path)
        findings: list[Finding] = []

        line_rules: list[tuple[str, re.Pattern[str], str, str, Severity, list[str], str, str]] = [
            (
                "general-security.cors-wildcard-credentials",
                re.compile(
                    r"(?:allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\].*allow_credentials\s*=\s*True|"
                    r"allow_credentials\s*=\s*True.*allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]|"
                    r"Access-Control-Allow-Origin[\"']\s*:\s*[\"']\*[\"'].*Access-Control-Allow-Credentials[\"']\s*:\s*[\"']true[\"'])"
                ),
                "Wildcard CORS origin ('*') combined with allow_credentials=True",
                (
                    "Configuring CORS with wildcard origin '*' and credentials enabled exposes authenticated "
                    "endpoints to cross-origin data theft."
                ),
                Severity.HIGH,
                ["CWE-942", "CWE-346"],
                "Replace wildcard '*' with an explicit allowlist of trusted origins when allow_credentials=True.",
                'app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"], allow_credentials=True)',
            ),
            (
                "general-security.insecure-token-comparison",
                re.compile(
                    r"\b(?:token|api_key|apikey|secret|signature|hmac_sig|auth_token|expected_token|provided_token)\b"
                    r"\s*(?:==|!=)\s*"
                    r"(?!None\b|True\b|False\b|[\"'][\"']\b)"
                    r"[A-Za-z0-9_.\[\]\"']+"
                ),
                "Non-constant-time comparison of security token or secret using '=='",
                (
                    "Comparing tokens, API keys, or cryptographic signatures with '==' or '!=' leaks timing "
                    "side-channel information."
                ),
                Severity.HIGH,
                ["CWE-208"],
                "Use hmac.compare_digest(a, b) or secrets.compare_digest(a, b) for constant-time comparison.",
                "if not hmac.compare_digest(provided_token, expected_token):",
            ),
            (
                "general-security.path-traversal",
                re.compile(
                    r"(?:\bopen\s*\(\s*(?:f[\"'][^\"']*\{[^}]*(?:user_path|filename|file_name|req_path|user_file)"
                    r"[^}]*\}|os\.path\.join\s*\([^)]*(?:user_path|filename|file_name|req_path|user_file)|"
                    r"[^)]*\+\s*(?:user_path|filename|file_name|req_path|user_file))|"
                    r"send_file\s*\(\s*(?:request\.|user_path|filename))"
                ),
                "Potential path traversal in file access with unvalidated user path",
                (
                    "User-supplied file path or filename is joined or opened without verifying that the resolved "
                    "path stays within the intended base directory."
                ),
                Severity.HIGH,
                ["CWE-22"],
                "Validate paths with nexcoder_core.sandbox.resolve_inside(base_dir, user_path) before opening files.",
                "safe_path = resolve_inside(base_dir, user_path)\ndata = safe_path.read_text(encoding='utf-8')",
            ),
            (
                "general-security.ssrf-unvalidated-url",
                re.compile(
                    r"(?:requests\s*\.\s*(?:get|post|put|request)|httpx\s*\.\s*(?:get|post|request)|"
                    r"urllib\.request\.urlopen)\s*\(\s*"
                    r"(?:user_url|target_url|webhook_url|callback_url|external_url|download_url|request\.)"
                ),
                "Potential Server-Side Request Forgery (SSRF) in outbound URL fetch",
                (
                    "Outbound HTTP client fetches a user-supplied URL without validating the scheme, host allowlist, "
                    "or blocking private/loopback/metadata IP ranges."
                ),
                Severity.HIGH,
                ["CWE-918"],
                (
                    "Validate the parsed URL against an explicit HTTPS host allowlist and reject loopback, "
                    "link-local (169.254.169.254), and RFC1918 private network addresses."
                ),
                (
                    "validate_allowed_outbound_url(user_url, allowed_hosts=ALLOWED_HOSTS)\n"
                    "resp = httpx.get(user_url, timeout=5.0)"
                ),
            ),
            (
                "general-security.shell-command-injection",
                re.compile(
                    r"(?:os\.(?:system|popen)\s*\(|subprocess\.(?:run|call|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True)"
                ),
                "Shell command execution with external input or shell=True",
                (
                    "Executing shell commands via os.system/popen or subprocess with shell=True enables "
                    "arbitrary command injection when untrusted input is present."
                ),
                Severity.CRITICAL,
                ["CWE-78"],
                "Pass command arguments as an explicit list with shell=False and validate inputs against an allowlist.",
                "subprocess.run(['git', 'status'], check=True, shell=False)",
            ),
        ]

        for file_path in _iter_source_files(target, {".py", ".js", ".ts"}):
            with contextlib.suppress(Exception):
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = source.splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    for rule_id, pattern, title, desc, sev, cwes, fix_summary, fixed_code in line_rules:
                        if pattern.search(line):
                            snippet = _safe_snippet(line)
                            diff = (
                                f"--- a/{file_path}\n+++ b/{file_path}\n"
                                f"@@ -{line_idx},1 +{line_idx},1 @@\n-{snippet}\n+{fixed_code}\n"
                            )
                            findings.append(
                                Finding(
                                    id=f"general-security-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=rule_id,
                                    title=title,
                                    description=f"{desc} ({file_path}:{line_idx})",
                                    severity=sev,
                                    category=FindingCategory.AUTH_SECURITY,
                                    location=Location(
                                        file_path=str(file_path),
                                        line_start=line_idx,
                                        line_end=line_idx,
                                        snippet=snippet,
                                    ),
                                    cwe_ids=cwes,
                                    remediation=Remediation(
                                        summary=fix_summary,
                                        diff_patch=diff,
                                    ),
                                    raw_data={"rule_id": rule_id, "line": line_idx},
                                )
                            )

                if file_path.suffix.lower() == ".py":
                    findings.extend(self._scan_python_ast_auth(file_path, source, lines, len(findings)))

        return self._create_result(target, findings, start_time, version="1.0.0-native", is_fallback=False)

    def _scan_python_ast_auth(
        self,
        file_path: Path,
        source: str,
        lines: list[str],
        start_idx: int,
    ) -> list[Finding]:
        """Inspect Python AST for unauthenticated routes and fail-open auth handlers."""
        ast_findings: list[Finding] = []
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return ast_findings

        public_paths = {
            "/health",
            "/healthz",
            "/ping",
            "/ready",
            "/live",
            "/docs",
            "/openapi.json",
            "/public",
            "/login",
        }
        auth_markers = {
            "auth",
            "authenticate",
            "authenticated",
            "require_auth",
            "login_required",
            "current_user",
            "current_principal",
            "principal",
            "verify_token",
            "require_admin",
            "require_role",
            "api_key",
            "depends",
            "security",
        }

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # 1. Check route decorators without authentication
            route_decorator_line: int | None = None
            route_path_str = ""
            has_auth_decorator = False

            for dec in node.decorator_list:
                dec_src = ast.unparse(dec).lower()
                if any(marker in dec_src for marker in auth_markers):
                    has_auth_decorator = True
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    method_name = dec.func.attr.lower()
                    owner_name = ast.unparse(dec.func.value).lower()
                    if method_name in {"get", "post", "put", "delete", "patch", "route"} and any(
                        r in owner_name for r in ("app", "router", "bp", "api", "blueprint")
                    ):
                        route_decorator_line = dec.lineno
                        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                            route_path_str = dec.args[0].value

            if route_decorator_line is not None and route_path_str not in public_paths:
                # Check function arguments and body for auth checks
                fn_args_src = ", ".join(ast.unparse(a).lower() for a in node.args.args)
                fn_defaults_src = ", ".join(ast.unparse(d).lower() for d in node.args.defaults)
                body_src = "\n".join(ast.unparse(stmt).lower() for stmt in node.body[:4])
                combined_auth_signals = f"{fn_args_src} {fn_defaults_src} {body_src}"

                if not has_auth_decorator and not any(m in combined_auth_signals for m in auth_markers):
                    line_no = route_decorator_line
                    raw_line = lines[line_no - 1] if 1 <= line_no <= len(lines) else f"def {node.name}(...):"
                    snippet = _safe_snippet(raw_line)
                    fixed_code = (
                        f"{raw_line.strip()}\n"
                        f"def {node.name}(..., principal: AuthPrincipal = Depends(require_authenticated)):"
                    )
                    diff = (
                        f"--- a/{file_path}\n+++ b/{file_path}\n"
                        f"@@ -{line_no},1 +{line_no},2 @@\n-{snippet}\n+{fixed_code}\n"
                    )
                    ast_findings.append(
                        Finding(
                            id=f"general-security-{start_idx + len(ast_findings) + 1}",
                            scanner=self.name,
                            rule_id="general-security.route-missing-auth",
                            title=f"Route '{route_path_str or node.name}' lacks authentication enforcement",
                            description=(
                                f"HTTP endpoint '{route_path_str or node.name}' in function '{node.name}' "
                                f"has no authentication decorator or principal dependency ({file_path}:{line_no})"
                            ),
                            severity=Severity.HIGH,
                            category=FindingCategory.AUTH_SECURITY,
                            location=Location(
                                file_path=str(file_path),
                                line_start=line_no,
                                line_end=node.lineno,
                                snippet=snippet,
                            ),
                            cwe_ids=["CWE-306", "CWE-862"],
                            remediation=Remediation(
                                summary=(
                                    "Protect the route with an authentication dependency (e.g., "
                                    "Depends(require_authenticated)) or @require_auth decorator that fails closed."
                                ),
                                diff_patch=diff,
                            ),
                            raw_data={
                                "rule_id": "general-security.route-missing-auth",
                                "function": node.name,
                                "route": route_path_str,
                                "line": line_no,
                            },
                        )
                    )

            # 2. Check auth functions that fail open (except Exception: return True / pass)
            if any(k in node.name.lower() for k in ("auth", "verify_token", "check_token", "check_permission")):
                for child in ast.walk(node):
                    if isinstance(child, ast.ExceptHandler):
                        for stmt in child.body:
                            is_return_true = (
                                isinstance(stmt, ast.Return)
                                and isinstance(stmt.value, ast.Constant)
                                and stmt.value.value is True
                            )
                            is_pass = isinstance(stmt, ast.Pass)
                            if is_return_true or is_pass:
                                line_no = getattr(stmt, "lineno", child.lineno)
                                raw_line = lines[line_no - 1] if 1 <= line_no <= len(lines) else "return True"
                                snippet = _safe_snippet(raw_line)
                                fixed_code = 'raise AuthenticationError("Authentication verification failed")'
                                diff = (
                                    f"--- a/{file_path}\n+++ b/{file_path}\n"
                                    f"@@ -{line_no},1 +{line_no},1 @@\n-{snippet}\n+{fixed_code}\n"
                                )
                                ast_findings.append(
                                    Finding(
                                        id=f"general-security-{start_idx + len(ast_findings) + 1}",
                                        scanner=self.name,
                                        rule_id="general-security.auth-fail-open",
                                        title=f"Authentication handler '{node.name}' fails open on exception",
                                        description=(
                                            f"Exception handler in '{node.name}' grants access or ignores errors "
                                            f"instead of failing closed ({file_path}:{line_no})"
                                        ),
                                        severity=Severity.CRITICAL,
                                        category=FindingCategory.AUTH_SECURITY,
                                        location=Location(
                                            file_path=str(file_path),
                                            line_start=line_no,
                                            line_end=line_no,
                                            snippet=snippet,
                                        ),
                                        cwe_ids=["CWE-636", "CWE-287"],
                                        remediation=Remediation(
                                            summary=(
                                                "Enforce fail-closed authentication: raise an AuthenticationError "
                                                "or return False when token verification raises an exception."
                                            ),
                                            diff_patch=diff,
                                        ),
                                        raw_data={
                                            "rule_id": "general-security.auth-fail-open",
                                            "function": node.name,
                                            "line": line_no,
                                        },
                                    )
                                )

        return ast_findings
