"""Tests for API Key management, USD spending caps, and rate limits."""

from __future__ import annotations

import pytest
from nexcoder_control.auth.base import AuthenticationError, ForbiddenError
from nexcoder_control.keys.models import APIKeyCreate
from nexcoder_control.keys.rate_limit import (
    CapExceededError,
    FixedWindowRateLimiter,
    RateLimitExceededError,
    TokenBucket,
)
from nexcoder_control.keys.store import APIKeyService


class TestAPIKeyService:
    def test_create_and_verify_key(self, key_service: APIKeyService) -> None:
        created = key_service.create_key(
            APIKeyCreate(
                name="Test Key",
                owner="team-alpha",
                usd_cap=10.0,
                rate_limit_rpm=100,
                scopes=["tools:read", "tools:execute"],
            )
        )
        assert created.raw_key.startswith("fc_key_")
        assert created.owner == "team-alpha"

        verified = key_service.verify_key(created.raw_key, required_scope="tools:execute")
        assert verified.key_id == created.key_id
        assert verified.owner == "team-alpha"

    def test_verify_invalid_key_fails_closed(self, key_service: APIKeyService) -> None:
        with pytest.raises(AuthenticationError):
            key_service.verify_key("fc_key_invalid_randomstring1234567890")

    def test_verify_inactive_key(self, key_service: APIKeyService) -> None:
        created = key_service.create_key(APIKeyCreate(name="Revocable Key"))
        key_service.revoke_key(created.key_id)

        with pytest.raises(AuthenticationError, match="disabled or revoked"):
            key_service.verify_key(created.raw_key)

    def test_scope_enforcement(self, key_service: APIKeyService) -> None:
        created = key_service.create_key(APIKeyCreate(name="Scoped Key", scopes=["tools:read"]))
        # Permitted scope
        key_service.verify_key(created.raw_key, required_scope="tools:read")

        # Missing scope fails closed (403)
        with pytest.raises(ForbiddenError, match="lacks required scope"):
            key_service.verify_key(created.raw_key, required_scope="tools:write")

    def test_usd_cap_enforcement(self, key_service: APIKeyService) -> None:
        created = key_service.create_key(APIKeyCreate(name="Capped Key", usd_cap=5.0))
        # Spend within cap
        key_service.verify_key(created.raw_key, estimated_usd=4.50)
        key_service.record_spend(created.key_id, cost_usd=4.50)

        # Additional spend exceeds cap (4.50 + 0.60 = 5.10 > 5.0) -> CapExceededError (403)
        with pytest.raises(CapExceededError, match="spend cap of \\$5.00 exceeded"):
            key_service.verify_key(created.raw_key, estimated_usd=0.60)

    def test_rate_limit_rpm_enforcement(self, key_service: APIKeyService) -> None:
        created = key_service.create_key(APIKeyCreate(name="Rate Limited Key", rate_limit_rpm=3))
        # 3 calls allowed
        for _ in range(3):
            key_service.verify_key(created.raw_key)

        # 4th call exceeds RPM -> 429 RateLimitExceededError
        with pytest.raises(RateLimitExceededError, match="Rate limit exceeded"):
            key_service.verify_key(created.raw_key)


class TestRateLimitingAlgorithms:
    def test_token_bucket(self) -> None:
        bucket = TokenBucket(capacity=5.0, refill_rate_per_sec=1.0)
        assert bucket.consume(3.0) is True
        assert bucket.consume(2.0) is True
        assert bucket.consume(1.0) is False  # Empty

    def test_fixed_window_rate_limiter(self) -> None:
        limiter = FixedWindowRateLimiter(window_seconds=60.0)
        allowed, count, _ = limiter.check_and_increment("client_1", limit=2, amount=1)
        assert allowed is True
        assert count == 1

        allowed, count, _ = limiter.check_and_increment("client_1", limit=2, amount=1)
        assert allowed is True
        assert count == 2

        # 3rd request rejected
        allowed, count, _ = limiter.check_and_increment("client_1", limit=2, amount=1)
        assert allowed is False
        assert count == 2
