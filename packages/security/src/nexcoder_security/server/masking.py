"""PII and sensitive data masking engine for logs, dumps (SQL/JSON/CSV), and non-prod environments."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

MaskingStrategy = Literal["placeholder", "redact", "hash"]
MaskingProfile = Literal["basic", "advanced"]


class MaskingRule(BaseModel):
    """Regex-based rule to match and mask sensitive data entities."""

    name: str
    pattern: str
    placeholder_prefix: str
    custom_replacer: Callable[[str], str] | None = None


DEFAULT_MASKING_RULES: list[MaskingRule] = [
    MaskingRule(
        name="email",
        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        placeholder_prefix="EMAIL",
    ),
    MaskingRule(
        name="cpf",
        pattern=r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
        placeholder_prefix="CPF",
    ),
    MaskingRule(
        name="cnpj",
        pattern=r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
        placeholder_prefix="CNPJ",
    ),
    MaskingRule(
        name="credit_card",
        pattern=r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        placeholder_prefix="CARD",
    ),
    MaskingRule(
        name="phone",
        pattern=r"\b(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\d{4}|\d{4})[-.\s]\d{4}\b",
        placeholder_prefix="PHONE",
    ),
    MaskingRule(
        name="ipv4",
        pattern=r"\b(?<!\d)(?:1\d\d|2[0-4]\d|25[0-5]|[1-9]?\d)\.(?:1\d\d|2[0-4]\d|25[0-5]|[1-9]?\d)\.(?:1\d\d|2[0-4]\d|25[0-5]|[1-9]?\d)\.(?:1\d\d|2[0-4]\d|25[0-5]|[1-9]?\d)(?!\d)\b",
        placeholder_prefix="IP",
    ),
    MaskingRule(
        name="secret_key",
        pattern=r"\b(?:sk-|fc_key_|ghp_|AKIA|eyJ)[A-Za-z0-9_-]{12,}\b",
        placeholder_prefix="SECRET",
    ),
    MaskingRule(
        name="bearer_token",
        pattern=r"\b(?:Bearer|Token)\s+([A-Za-z0-9._~+/-]{16,})\b",
        placeholder_prefix="AUTH_TOKEN",
    ),
]

SECRET_KEY_NAMES: set[str] = {
    "password",
    "secret",
    "token",
    "auth_token",
    "access_token",
    "refresh_token",
    "api_key",
    "credential",
    "private_key",
    "cvv",
}


class DataMasker:
    """Anonymizes and masks personal data and secrets across logs, SQL dumps, JSON, and CSVs."""

    def __init__(
        self,
        strategy: MaskingStrategy = "placeholder",
        profile: MaskingProfile = "basic",
        custom_rules: list[MaskingRule] | None = None,
        salt: str = "nexcoder-default-salt",
    ) -> None:
        self.strategy = strategy
        self.profile = profile
        self.salt = salt
        self.rules = custom_rules or list(DEFAULT_MASKING_RULES)
        self._compiled = [(r, re.compile(r.pattern, re.IGNORECASE)) for r in self.rules]
        self.mapping: dict[str, str] = {}
        self._reverse_mapping: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    @classmethod
    def basic(cls) -> DataMasker:
        """Create basic masker with deterministic placeholder substitution."""
        return cls(strategy="placeholder", profile="basic")

    @classmethod
    def advanced(cls, salt: str, strategy: MaskingStrategy = "hash") -> DataMasker:
        """Create advanced masker with cryptographic salted hashing."""
        return cls(strategy=strategy, profile="advanced", salt=salt)

    def _generate_replacement(self, value: str, prefix: str) -> str:
        """Compute the replacement string based on selected strategy."""
        if value in self.mapping:
            return self.mapping[value]

        if self.strategy == "placeholder":
            count = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = count
            replacement = f"[{prefix}_{count}]"
        elif self.strategy == "hash":
            digest = hmac.new(self.salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
            replacement = f"[{prefix}_{digest}]"
        else:  # redact
            if prefix == "EMAIL":
                parts = value.split("@", 1)
                replacement = f"***@{parts[1]}" if len(parts) == 2 else "***@***.***"
            elif prefix in {"CPF", "CNPJ", "CARD"}:
                replacement = f"***_{prefix}"
            else:
                replacement = f"[{prefix}_REDACTED]"

        self.mapping[value] = replacement
        self._reverse_mapping[replacement] = value
        return replacement

    def mask_text(self, text: str) -> str:
        """Mask all matched PII entities in a text string."""
        if not text:
            return text

        result = text

        # 1. Mask connection string passwords: e.g. postgres://user:password@host
        def _uri_repl(m: re.Match[str]) -> str:
            prefix, secret, suffix = m.group(1), m.group(2), m.group(3)
            masked_secret = self._generate_replacement(secret, "PASSWORD")
            return f"{prefix}{masked_secret}{suffix}"

        result = re.sub(
            r"((?:postgres|postgresql|mysql|mongodb|redis|amqp|https?)://[^:]+:)([^@/]+)(@)",
            _uri_repl,
            result,
        )

        # 2. Mask regex rules
        for rule, regex in self._compiled:
            prefix = rule.placeholder_prefix

            def _repl(match: re.Match[str], p: str = prefix) -> str:
                # Handle grouping (e.g. Bearer <token>)
                val = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                rep = self._generate_replacement(val, p)
                if match.lastindex and match.lastindex >= 1:
                    full = match.group(0)
                    return full.replace(val, rep)
                return rep

            result = regex.sub(_repl, result)

        return result

    def unmask_text(self, text: str) -> str:
        """Restore original values from placeholders (only valid for placeholder strategy)."""
        if not text or not self._reverse_mapping:
            return text

        result = text
        for placeholder, original in self._reverse_mapping.items():
            result = result.replace(placeholder, original)
        return result

    def mask_log_line(self, line: str) -> str:
        """Mask a single log line."""
        return self.mask_text(line)

    def mask_log_file(self, content: str) -> str:
        """Mask an entire log file line by line."""
        return "\n".join(self.mask_log_line(line) for line in content.splitlines())

    def mask_json(self, data: Any) -> Any:
        """Recursively mask sensitive values inside a JSON-serializable structure or string."""
        if isinstance(data, str):
            # Check if string itself is valid JSON
            try:
                parsed = json.loads(data)
                masked_obj = self.mask_json(parsed)
                return json.dumps(masked_obj, indent=2)
            except Exception:
                return self.mask_text(data)

        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for k, v in data.items():
                is_secret_key = any(sens in k.lower() for sens in SECRET_KEY_NAMES)
                if is_secret_key and isinstance(v, str):
                    out[k] = self._generate_replacement(v, "SECRET")
                elif isinstance(v, (dict, list)):
                    out[k] = self.mask_json(v)
                elif isinstance(v, str):
                    out[k] = self.mask_text(v)
                else:
                    out[k] = v
            return out

        if isinstance(data, list):
            return [self.mask_json(item) for item in data]

        return data

    def mask_sql_dump(self, sql_content: str) -> str:
        """Mask sensitive data in SQL INSERT statements while preserving valid SQL syntax."""
        lines = sql_content.splitlines()
        masked_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Check if line contains INSERT INTO ... VALUES (...)
            if re.search(r"\bINSERT\s+INTO\s+.*?\bVALUES\b", stripped, re.IGNORECASE):
                # Mask string literals between single quotes
                def _quote_repl(m: re.Match[str]) -> str:
                    quote_content = m.group(1)
                    masked = self.mask_text(quote_content)
                    return f"'{masked}'"

                # Match single quoted SQL strings: 'something'
                masked_line = re.sub(r"'([^']*)'", _quote_repl, line)
                masked_lines.append(masked_line)
            else:
                masked_lines.append(self.mask_text(line))

        return "\n".join(masked_lines)

    def mask_csv(self, csv_content: str, delimiter: str = ",") -> str:
        """Mask tabular CSV/TSV content row by row."""
        input_stream = io.StringIO(csv_content)
        reader = csv.reader(input_stream, delimiter=delimiter)
        output_stream = io.StringIO()
        writer = csv.writer(output_stream, delimiter=delimiter, lineterminator="\n")

        for row in reader:
            masked_row = [self.mask_text(cell) for cell in row]
            writer.writerow(masked_row)

        return output_stream.getvalue()

    def mask_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Recursively anonymize all sensitive strings inside a dictionary record."""
        return self.mask_json(record)  # type: ignore[return-value]
