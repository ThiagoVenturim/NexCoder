"""Public and legitimate business data sources for prospecting.

Only sources that declare an acceptable kind (official API, open data or a licensed
directory) and whose terms allow automated access are accepted. Scraped or purchased
contact lists are refused. Records are minimized to business-level fields; anything
else in the raw record (for example names of partners or owners) is dropped.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from nexcoder_agents.leadgen.models import BusinessCandidate, LeadGenPolicyError, SearchQuery, SourceKind

# Raw record keys that are copied into a BusinessCandidate. Everything else is discarded.
ALLOWED_FIELDS = ("business_id", "name", "segment", "region", "website", "public_email", "public_phone", "address")

_FORBIDDEN_SOURCE_HINTS = ("scrap", "purchased", "bought", "leaked", "harvest", "comprad", "raspad")
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),  # CPF (individual taxpayer id)
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
)


@runtime_checkable
class BusinessSource(Protocol):
    """A business data source. Implementations must use an official API, open data or a licensed directory."""

    name: str
    kind: SourceKind
    terms_reference: str
    allows_automated_access: bool

    def search(self, query: SearchQuery) -> list[BusinessCandidate]:
        """Return business candidates for a region and segment."""
        ...


def ensure_legitimate_source(source: Any) -> None:
    """Refuse sources that are not declared as public and legitimate."""
    name = str(getattr(source, "name", "") or "")
    kind = getattr(source, "kind", None)
    if not name:
        raise LeadGenPolicyError("Business source must declare a name")
    try:
        SourceKind(kind)
    except ValueError as exc:
        raise LeadGenPolicyError(
            f"Source '{name}' kind '{kind}' is not accepted. Use an official API, open data or a licensed directory."
        ) from exc
    if not getattr(source, "allows_automated_access", False):
        raise LeadGenPolicyError(f"Source '{name}' does not declare that its terms allow automated access")
    if not str(getattr(source, "terms_reference", "") or "").strip():
        raise LeadGenPolicyError(f"Source '{name}' must reference the terms of use that allow this access")
    lowered = name.lower()
    if any(hint in lowered for hint in _FORBIDDEN_SOURCE_HINTS):
        raise LeadGenPolicyError(f"Source '{name}' looks like a scraped or purchased list, which is not allowed")


def _contains_sensitive_value(value: str) -> bool:
    return any(p.search(value) for p in _SENSITIVE_VALUE_PATTERNS)


def minimize_record(
    raw: Mapping[str, Any],
    *,
    source_name: str,
    source_kind: SourceKind,
    source_reference: str = "",
    default_region: str = "",
    default_segment: str = "",
) -> BusinessCandidate | None:
    """Keep only business-level fields. Returns None when the record has no business name."""
    data: dict[str, Any] = {}
    for key in ALLOWED_FIELDS:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or _contains_sensitive_value(text):
            continue
        data[key] = text
    name = data.get("name")
    if not name:
        return None
    if "business_id" not in data:
        digest = hashlib.sha256(f"{source_name}:{name}:{data.get('address', '')}".encode()).hexdigest()
        data["business_id"] = f"biz_{digest[:12]}"
    data.setdefault("region", default_region)
    data.setdefault("segment", default_segment)
    return BusinessCandidate(
        **data,
        source=source_name,
        source_kind=source_kind,
        source_reference=source_reference,
    )


def _matches(candidate: BusinessCandidate, query: SearchQuery) -> bool:
    region = query.region.strip().lower()
    segment = query.segment.strip().lower()
    return region in candidate.region.lower() and segment in candidate.segment.lower()


class StaticBusinessSource:
    """In-memory source built from records already obtained from a legitimate source (also used in tests)."""

    def __init__(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        name: str = "static-open-data",
        kind: SourceKind = SourceKind.OPEN_DATA,
        terms_reference: str = "Records supplied by the operator from a source whose terms allow reuse.",
        allows_automated_access: bool = True,
    ) -> None:
        self.name = name
        self.kind = kind
        self.terms_reference = terms_reference
        self.allows_automated_access = allows_automated_access
        self._records = [dict(r) for r in records]

    def search(self, query: SearchQuery) -> list[BusinessCandidate]:
        results: list[BusinessCandidate] = []
        for raw in self._records:
            cand = minimize_record(raw, source_name=self.name, source_kind=self.kind)
            if cand is not None and _matches(cand, query):
                results.append(cand)
            if len(results) >= query.limit:
                break
        return results


class CsvOpenDataSource(StaticBusinessSource):
    """Local CSV export downloaded by the operator from an open data portal.

    The CSV must use the column names in ALLOWED_FIELDS. Other columns are ignored.
    """

    def __init__(self, csv_path: str | Path, *, name: str = "csv-open-data", terms_reference: str) -> None:
        path = Path(csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Open data file not found: {csv_path}")
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        super().__init__(rows, name=name, kind=SourceKind.OPEN_DATA, terms_reference=terms_reference)
