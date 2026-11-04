"""Budget policies, multi-threshold alerting, and fail-closed limit enforcement."""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from faccoder_control.metering.cost_tracker import CostTracker, DimensionType


class BudgetExceededError(Exception):
    """Raised when a budget hard limit is exceeded."""

    def __init__(
        self,
        message: str = "Budget limit exceeded",
        current_spend: float = 0.0,
        limit_usd: float = 0.0,
        entity_id: str = "",
        status_code: int = 403,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.current_spend = current_spend
        self.limit_usd = limit_usd
        self.entity_id = entity_id
        self.status_code = status_code


class BudgetPolicy(BaseModel):
    """Configuration for spending limits and alerting thresholds."""

    policy_id: str = Field(default_factory=lambda: f"pol_{uuid.uuid4().hex[:12]}")
    dimension: DimensionType
    entity_id: str  # e.g. "app_billing", "alice@example.com", "code-intel-agent"
    limit_usd: float
    thresholds: list[float] = Field(default_factory=lambda: [0.8, 1.0])
    enforce_hard_limit: bool = True
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetAlert(BaseModel):
    """Notification emitted when spend crosses a budget threshold."""

    alert_id: str
    policy_id: str
    dimension: DimensionType
    entity_id: str
    threshold: float
    current_spend_usd: float
    limit_usd: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: str


class BudgetManager:
    """Manages budgets, evaluates spending against policies, and emits threshold alerts."""

    def __init__(self, cost_tracker: CostTracker) -> None:
        self.cost_tracker = cost_tracker
        self._policies: dict[str, BudgetPolicy] = {}  # policy_id -> policy
        self._fired_thresholds: dict[tuple[str, float], datetime] = {}  # (policy_id, threshold) -> timestamp
        self._alerts: list[BudgetAlert] = []
        self._listeners: list[Callable[[BudgetAlert], None]] = []
        self._lock = threading.Lock()

    def add_policy(self, policy: BudgetPolicy) -> None:
        """Register or update a budget policy."""
        with self._lock:
            self._policies[policy.policy_id] = policy.model_copy()

    def set_policy(self, policy: BudgetPolicy) -> None:
        """Alias for add_policy."""
        self.add_policy(policy)

    def get_policy(self, policy_id: str) -> BudgetPolicy | None:
        with self._lock:
            p = self._policies.get(policy_id)
            return p.model_copy() if p else None

    def list_policies(self) -> list[BudgetPolicy]:
        with self._lock:
            return [p.model_copy() for p in self._policies.values()]

    def register_alert_listener(self, listener: Callable[[BudgetAlert], None]) -> None:
        """Register a callback invoked when a threshold is breached."""
        with self._lock:
            self._listeners.append(listener)

    def evaluate_entity(
        self,
        dimension: DimensionType,
        entity_id: str,
        additional_usd: float = 0.0,
    ) -> list[BudgetAlert]:
        """Evaluate spending for an entity, emit alerts if thresholds crossed, and enforce hard limits."""
        with self._lock:
            active_policies = [
                p
                for p in self._policies.values()
                if p.is_active and p.dimension == dimension and p.entity_id in (entity_id, "*")
            ]

        if not active_policies:
            return []

        summaries = self.cost_tracker.aggregate_by(dimension)
        summary = summaries.get(entity_id)
        current_spend = (summary.total_cost_usd if summary else 0.0) + additional_usd

        new_alerts: list[BudgetAlert] = []

        for policy in active_policies:
            ratio = current_spend / policy.limit_usd if policy.limit_usd > 0 else 1.0

            for threshold in sorted(policy.thresholds):
                if ratio >= threshold:
                    key = (policy.policy_id, threshold)
                    with self._lock:
                        if key not in self._fired_thresholds:
                            self._fired_thresholds[key] = datetime.now(UTC)
                            alert = BudgetAlert(
                                alert_id=f"alt_{len(self._alerts) + 1}",
                                policy_id=policy.policy_id,
                                dimension=policy.dimension,
                                entity_id=policy.entity_id,
                                threshold=threshold,
                                current_spend_usd=current_spend,
                                limit_usd=policy.limit_usd,
                                message=(
                                    f"Spend of ${current_spend:.4f} reached {threshold * 100:.0f}% "
                                    f"of budget (${policy.limit_usd:.2f}) for {dimension} '{entity_id}'"
                                ),
                            )
                            self._alerts.append(alert)
                            new_alerts.append(alert)
                            listeners = list(self._listeners)
                            for listener in listeners:
                                with contextlib.suppress(Exception):
                                    listener(alert)

            # Fail closed on hard limit
            if policy.enforce_hard_limit and current_spend > policy.limit_usd:
                raise BudgetExceededError(
                    f"Budget hard limit of ${policy.limit_usd:.2f} exceeded for {dimension} '{entity_id}' "
                    f"(current spend: ${current_spend:.4f})",
                    current_spend=current_spend,
                    limit_usd=policy.limit_usd,
                    entity_id=entity_id,
                )

        return new_alerts

    def get_alerts(self) -> list[BudgetAlert]:
        """Return history of emitted budget alerts."""
        with self._lock:
            return list(self._alerts)
