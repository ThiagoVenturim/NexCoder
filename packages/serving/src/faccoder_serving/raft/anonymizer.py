"""PII and secret anonymization engine for fine-tuning datasets and training pipelines."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel


class AnonymizationRule(BaseModel):
    name: str
    pattern: str
    placeholder_prefix: str


DEFAULT_RULES: list[AnonymizationRule] = [
    AnonymizationRule(
        name="email",
        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        placeholder_prefix="EMAIL",
    ),
    AnonymizationRule(
        name="cpf",
        pattern=r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
        placeholder_prefix="CPF",
    ),
    AnonymizationRule(
        name="cnpj",
        pattern=r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
        placeholder_prefix="CNPJ",
    ),
    AnonymizationRule(
        name="phone",
        pattern=r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})[-.\s]?\d{4}\b",
        placeholder_prefix="PHONE",
    ),
    AnonymizationRule(
        name="credit_card",
        pattern=r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        placeholder_prefix="CARD",
    ),
    AnonymizationRule(
        name="ipv4",
        pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        placeholder_prefix="IP",
    ),
    AnonymizationRule(
        name="secret_key",
        pattern=r"\b(?:sk-|fc_key_|ghp_|AKIA|eyJ)[A-Za-z0-9_-]{12,}\b",
        placeholder_prefix="SECRET",
    ),
]


class Anonymizer:
    """Anonymizes sensitive PII and secrets deterministically across text and datasets."""

    def __init__(self, custom_rules: list[AnonymizationRule] | None = None) -> None:
        self.rules = custom_rules or DEFAULT_RULES
        self._compiled = [(r, re.compile(r.pattern, re.IGNORECASE)) for r in self.rules]
        self.mapping: dict[str, str] = {}
        self._reverse_mapping: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def _get_placeholder(self, value: str, prefix: str) -> str:
        """Get or assign a consistent placeholder for a sensitive value."""
        if value in self.mapping:
            return self.mapping[value]

        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        placeholder = f"[{prefix}_{count}]"
        self.mapping[value] = placeholder
        self._reverse_mapping[placeholder] = value
        return placeholder

    def anonymize_text(self, text: str) -> str:
        """Scan text and replace all matched PII entities with placeholders."""
        if not text:
            return text

        result = text
        for rule, regex in self._compiled:
            prefix = rule.placeholder_prefix

            def _repl(match: re.Match[str], p: str = prefix) -> str:
                return self._get_placeholder(match.group(0), p)

            result = regex.sub(_repl, result)

        return result

    def deanonymize_text(self, text: str) -> str:
        """Restore original values from placeholders using the internal mapping."""
        if not text or not self._reverse_mapping:
            return text

        result = text
        for placeholder, original in self._reverse_mapping.items():
            result = result.replace(placeholder, original)
        return result

    def anonymize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Recursively anonymize all string values inside a dictionary or record."""
        out: dict[str, Any] = {}
        for k, v in record.items():
            if isinstance(v, str):
                out[k] = self.anonymize_text(v)
            elif isinstance(v, dict):
                out[k] = self.anonymize_record(v)
            elif isinstance(v, list):
                out[k] = [self.anonymize_text(i) if isinstance(i, str) else i for i in v]
            else:
                out[k] = v
        return out
