from __future__ import annotations

import re
from typing import Any

# Patterns targeting common sensitive credentials and tokens
_SECRET_PATTERNS = [
    # GitHub personal access tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
    # OpenAI and generic sk- tokens
    re.compile(r"sk-[A-Za-z0-9-_]{20,255}"),
    # AWS access key ID
    re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    # Generic bearer tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.~+/]+=*"),
    # Passwords in key-value format (e.g. password: xyz, pwd=xyz)
    re.compile(r"(?i)(password|passwd|pwd|secret|api_key|apikey|access_token|auth_token)\s*[:=]\s*['\"]?([^\s,;'\"]+)['\"]?"),
    # Connection strings with credentials
    re.compile(r"(?i)([a-z0-9+]+)://([^:\s]+):([^@\s]+)@"),
    # Private keys
    re.compile(r"-----BEGIN[ A-Z_-]*PRIVATE KEY-----.*?-----END[ A-Z_-]*PRIVATE KEY-----", re.DOTALL),
]


def sanitize_text(text: str) -> str:
    """Sanitize free text by replacing detected credentials, tokens, or passwords with a redacted placeholder."""
    if not text:
        return text

    sanitized = text
    for pattern in _SECRET_PATTERNS:
        # If it's a key-value password match with capture groups
        if pattern.pattern.startswith("(?i)(password"):
            sanitized = pattern.sub(r"\1: [REDACTED_SECRET]", sanitized)
        elif pattern.pattern.startswith("(?i)([a-z0-9+]+)"):
            sanitized = pattern.sub(r"\1://\2:[REDACTED_PASSWORD]@", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

    return sanitized


def sanitize_data(data: Any) -> Any:
    """Recursively sanitize dicts, lists, strings, and primitives."""
    if isinstance(data, str):
        return sanitize_text(data)
    if isinstance(data, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, value in data.items():
            # Check if key itself indicates a sensitive credential
            key_lower = str(key).lower()
            if any(s in key_lower for s in ("password", "secret", "token", "credential", "private_key")):
                sanitized_dict[key] = "[REDACTED_SECRET]"
            else:
                sanitized_dict[key] = sanitize_data(value)
        return sanitized_dict
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data
