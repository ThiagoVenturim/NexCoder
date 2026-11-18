"""Thread-safe registry for campaign reports and tracking."""

from __future__ import annotations

import threading
from typing import Any

from nexcoder_security.campaign.models import CampaignReport


class CampaignRegistry:
    """Thread-safe storage for past and in-progress campaign reports."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: dict[str, CampaignReport] = {}

    def register(self, report: CampaignReport) -> None:
        """Register or update a campaign report."""
        with self._lock:
            self._reports[report.campaign_id] = report.model_copy(deep=True)

    def get(self, campaign_id: str) -> CampaignReport | None:
        """Retrieve a campaign report by ID."""
        with self._lock:
            report = self._reports.get(campaign_id)
            return report.model_copy(deep=True) if report else None

    def list_campaigns(self, limit: int = 50) -> list[dict[str, Any]]:
        """List summary dictionaries of stored campaigns."""
        with self._lock:
            items = list(self._reports.values())
        items.sort(key=lambda r: r.authorized_at, reverse=True)
        return [
            {
                "campaign_id": r.campaign_id,
                "target": r.target,
                "status": r.status.value,
                "authorized_by": r.authorized_by,
                "agent_count": r.agent_count,
                "test_types": [t.value for t in r.test_types],
                "duration_seconds": r.duration_seconds,
                "cost_usd": r.actual_cost_usd,
                "findings_count": len(r.findings),
                "created_at": r.authorized_at.isoformat(),
            }
            for r in items[:limit]
        ]

    def clear(self) -> None:
        """Clear all stored campaign reports."""
        with self._lock:
            self._reports.clear()


_GLOBAL_REGISTRY = CampaignRegistry()


def get_global_registry() -> CampaignRegistry:
    """Return the global default campaign registry instance."""
    return _GLOBAL_REGISTRY
