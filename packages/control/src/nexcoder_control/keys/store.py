"""API Key store and verification service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from nexcoder_control.auth.base import AuthenticationError, ForbiddenError
from nexcoder_control.keys.models import APIKeyCreate, APIKeyCreatedResult, APIKeyRecord
from nexcoder_control.keys.rate_limit import (
    CapExceededError,
    FixedWindowRateLimiter,
    RateLimitExceededError,
    TokenBucket,
)


class BaseAPIKeyStore(ABC):
    """Abstract interface for persisting and querying API keys."""

    @abstractmethod
    def save(self, record: APIKeyRecord) -> None: ...

    @abstractmethod
    def get(self, key_id: str) -> APIKeyRecord | None: ...

    @abstractmethod
    def find_by_prefix(self, prefix: str) -> list[APIKeyRecord]: ...

    @abstractmethod
    def list_all(self) -> list[APIKeyRecord]: ...

    @abstractmethod
    def update_spend(self, key_id: str, additional_usd: float) -> APIKeyRecord: ...

    @abstractmethod
    def revoke(self, key_id: str) -> bool: ...


class InMemoryAPIKeyStore(BaseAPIKeyStore):
    """Thread-safe in-memory API key store."""

    def __init__(self) -> None:
        self._keys: dict[str, APIKeyRecord] = {}  # key_id -> record
        self._prefix_index: dict[str, list[str]] = {}  # prefix -> list of key_ids
        self._lock = threading.Lock()

    def save(self, record: APIKeyRecord) -> None:
        with self._lock:
            self._keys[record.key_id] = record.model_copy()
            if record.prefix not in self._prefix_index:
                self._prefix_index[record.prefix] = []
            if record.key_id not in self._prefix_index[record.prefix]:
                self._prefix_index[record.prefix].append(record.key_id)

    def get(self, key_id: str) -> APIKeyRecord | None:
        with self._lock:
            rec = self._keys.get(key_id)
            return rec.model_copy() if rec else None

    def find_by_prefix(self, prefix: str) -> list[APIKeyRecord]:
        with self._lock:
            ids = self._prefix_index.get(prefix, [])
            return [self._keys[kid].model_copy() for kid in ids if kid in self._keys]

    def list_all(self) -> list[APIKeyRecord]:
        with self._lock:
            return [rec.model_copy() for rec in self._keys.values()]

    def update_spend(self, key_id: str, additional_usd: float) -> APIKeyRecord:
        with self._lock:
            rec = self._keys.get(key_id)
            if not rec:
                raise KeyError(f"API key '{key_id}' not found")
            updated = rec.model_copy(update={"current_spend_usd": rec.current_spend_usd + additional_usd})
            self._keys[key_id] = updated
            return updated.model_copy()

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            rec = self._keys.get(key_id)
            if not rec:
                return False
            self._keys[key_id] = rec.model_copy(update={"is_active": False})
            return True


class APIKeyService:
    """Service managing API key lifecycle, verification, USD caps, and rate limits."""

    def __init__(
        self,
        store: BaseAPIKeyStore | None = None,
        rate_limiter: FixedWindowRateLimiter | None = None,
    ) -> None:
        self.store = store or InMemoryAPIKeyStore()
        self.rate_limiter = rate_limiter or FixedWindowRateLimiter(window_seconds=60.0)
        self._buckets: dict[str, TokenBucket] = {}
        self._bucket_lock = threading.Lock()

    def create_key(self, spec: APIKeyCreate) -> APIKeyCreatedResult:
        """Create a new API key, store its hash, and return the raw secret (once)."""
        random_suffix = secrets.token_urlsafe(32)
        key_id = f"key_{secrets.token_hex(8)}"
        prefix = f"fc_key_{key_id[-8:]}"
        raw_key = f"{prefix}_{random_suffix}"

        hashed_secret = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=spec.ttl_days) if spec.ttl_days else None

        record = APIKeyRecord(
            key_id=key_id,
            name=spec.name,
            prefix=prefix,
            hashed_secret=hashed_secret,
            owner=spec.owner,
            scopes=list(spec.scopes),
            usd_cap=spec.usd_cap,
            rate_limit_rpm=spec.rate_limit_rpm,
            rate_limit_tpm=spec.rate_limit_tpm,
            created_at=now,
            expires_at=expires_at,
            is_active=True,
            metadata=dict(spec.metadata),
        )

        self.store.save(record)

        return APIKeyCreatedResult(
            key_id=key_id,
            name=spec.name,
            prefix=prefix,
            raw_key=raw_key,
            owner=spec.owner,
            scopes=list(spec.scopes),
            usd_cap=spec.usd_cap,
            rate_limit_rpm=spec.rate_limit_rpm,
            expires_at=expires_at,
        )

    def verify_key(
        self,
        raw_key: str,
        required_scope: str | None = None,
        estimated_usd: float = 0.0,
        tokens_count: int = 0,
    ) -> APIKeyRecord:
        """Verify API key authenticity, active state, scopes, rate limits, and USD cap.

        Fails closed on any violation:
        - 401 AuthenticationError if key is invalid/expired/inactive.
        - 403 ForbiddenError if scope missing.
        - 403 CapExceededError if cumulative spend exceeds cap.
        - 429 RateLimitExceededError if rate limit is exceeded.
        """
        clean_key = raw_key.strip()
        if not clean_key or "_" not in clean_key:
            raise AuthenticationError("Malformed API key format")

        parts = clean_key.split("_", 2)
        if len(parts) < 3:
            raise AuthenticationError("Malformed API key structure")
        prefix = f"{parts[0]}_{parts[1]}_{parts[2].split('_')[0]}" if len(parts) > 2 else f"{parts[0]}_{parts[1]}"

        candidates = self.store.find_by_prefix(prefix)
        if not candidates:
            # Fallback scan in case prefix format diverges
            candidates = self.store.list_all()

        computed_hash = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()
        matched: APIKeyRecord | None = None

        for cand in candidates:
            if hmac.compare_digest(cand.hashed_secret, computed_hash):
                matched = cand
                break

        if not matched:
            raise AuthenticationError("Invalid API key")

        if not matched.is_active:
            raise AuthenticationError("API key is disabled or revoked")

        if matched.is_expired():
            raise AuthenticationError("API key has expired")

        # Scope validation
        if required_scope is not None and not matched.has_scope(required_scope):
            raise ForbiddenError(f"API key lacks required scope '{required_scope}'")

        # USD Cap check (Fail closed with 403 CapExceededError)
        if matched.usd_cap is not None:
            if matched.current_spend_usd + estimated_usd > matched.usd_cap:
                raise CapExceededError(
                    f"API key spend cap of ${matched.usd_cap:.2f} exceeded "
                    f"(current spend: ${matched.current_spend_usd:.4f})"
                )

        # Rate Limit check (Fail closed with 429 RateLimitExceededError)
        if matched.rate_limit_rpm is not None:
            allowed, count, reset_sec = self.rate_limiter.check_and_increment(
                key=f"rpm:{matched.key_id}",
                limit=matched.rate_limit_rpm,
                amount=1,
            )
            if not allowed:
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {count}/{matched.rate_limit_rpm} req/min. Retry in {reset_sec:.1f}s",
                    retry_after_seconds=reset_sec,
                )

        if matched.rate_limit_tpm is not None and tokens_count > 0:
            allowed, count, reset_sec = self.rate_limiter.check_and_increment(
                key=f"tpm:{matched.key_id}",
                limit=matched.rate_limit_tpm,
                amount=tokens_count,
            )
            if not allowed:
                raise RateLimitExceededError(
                    f"Token rate limit exceeded: {count}/{matched.rate_limit_tpm} tokens/min. "
                    f"Retry in {reset_sec:.1f}s",
                    retry_after_seconds=reset_sec,
                )

        return matched

    def record_spend(self, key_id: str, cost_usd: float) -> APIKeyRecord:
        """Record realized spend against the API key."""
        return self.store.update_spend(key_id, cost_usd)

    def revoke_key(self, key_id: str) -> bool:
        """Revoke API key."""
        return self.store.revoke(key_id)

    def list_keys(self) -> list[APIKeyRecord]:
        """List all stored API keys."""
        return self.store.list_all()
