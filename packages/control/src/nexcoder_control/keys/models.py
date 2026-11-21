"""API Key domain models and validation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class APIKeyRecord(BaseModel):
    """Persisted API key metadata (secret is stored hashed)."""

    key_id: str
    name: str
    prefix: str
    hashed_secret: str
    owner: str = "anonymous"
    scopes: list[str] = Field(default_factory=list)
    usd_cap: float | None = None
    current_spend_usd: float = 0.0
    rate_limit_rpm: int | None = None  # Requests per minute
    rate_limit_tpm: int | None = None  # Tokens per minute
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def is_cap_exceeded(self, additional_usd: float = 0.0) -> bool:
        if self.usd_cap is None:
            return False
        return (self.current_spend_usd + additional_usd) > self.usd_cap

    def has_scope(self, required_scope: str) -> bool:
        if not self.is_active or self.is_expired():
            return False
        if "*" in self.scopes:
            return True
        if required_scope in self.scopes:
            return True
        if ":" in required_scope:
            ns = required_scope.split(":", 1)[0]
            if f"{ns}:*" in self.scopes:
                return True
        return False


class APIKeyCreate(BaseModel):
    """Specification for creating a new API key."""

    name: str
    owner: str = "anonymous"
    scopes: list[str] = Field(default_factory=lambda: ["tools:execute", "metrics:read"])
    usd_cap: float | None = None
    rate_limit_rpm: int | None = None
    rate_limit_tpm: int | None = None
    ttl_days: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class APIKeyCreatedResult(BaseModel):
    """Result returned on key creation; raw_key is presented only once."""

    key_id: str
    name: str
    prefix: str
    raw_key: str
    owner: str
    scopes: list[str]
    usd_cap: float | None
    rate_limit_rpm: int | None
    expires_at: datetime | None
