"""API Key store and verification service."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

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


class SQLAlchemyAPIKeyStore(BaseAPIKeyStore):
    """Thread-safe persistent API key store backed by SQLAlchemy."""

    def __init__(self, db_url: str | None = None, engine: Any = None) -> None:
        from nexcoder_core.store.db import create_db_engine, get_metadata, init_db

        self.engine = engine or create_db_engine(db_url)
        self.metadata = get_metadata()
        init_db(self.engine)
        self._table = self.metadata.tables["api_keys"]

    def _row_to_record(self, row: Any) -> APIKeyRecord:
        if isinstance(row.allowed_models, str):
            allowed_models = json.loads(row.allowed_models)
        else:
            allowed_models = row.allowed_models or []

        if isinstance(row.metadata_json, str):
            metadata_json = json.loads(row.metadata_json)
        else:
            metadata_json = row.metadata_json or {}

        return APIKeyRecord(
            key_id=row.key_id,
            name=row.name,
            prefix=row.prefix,
            hashed_secret=row.hashed_secret,
            owner=row.owner,
            scopes=allowed_models,
            usd_cap=row.budget_limit_usd,
            current_spend_usd=float(row.current_spend_usd or 0.0),
            rate_limit_rpm=row.rate_limit_rpm,
            rate_limit_tpm=None,
            created_at=row.created_at,
            expires_at=row.expires_at,
            is_active=bool(row.is_active),
            metadata=metadata_json,
        )

    def save(self, record: APIKeyRecord) -> None:
        with self.engine.begin() as conn:
            check_stmt = select(self._table.c.key_id).where(self._table.c.key_id == record.key_id)
            existing = conn.execute(check_stmt).fetchone()

            values = {
                "name": record.name,
                "prefix": record.prefix,
                "hashed_secret": record.hashed_secret,
                "owner": record.owner,
                "tier": record.metadata.get("tier", "standard"),
                "is_active": record.is_active,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
                "current_spend_usd": record.current_spend_usd,
                "budget_limit_usd": record.usd_cap,
                "rate_limit_rpm": record.rate_limit_rpm or 60,
                "allowed_models": json.dumps(record.scopes),
                "allowed_endpoints": json.dumps([]),
                "metadata_json": json.dumps(record.metadata, default=str),
            }

            if existing:
                update_stmt = self._table.update().where(self._table.c.key_id == record.key_id).values(**values)
                conn.execute(update_stmt)
            else:
                insert_stmt = self._table.insert().values(key_id=record.key_id, **values)
                conn.execute(insert_stmt)

    def get(self, key_id: str) -> APIKeyRecord | None:
        with self.engine.connect() as conn:
            stmt = select(self._table).where(self._table.c.key_id == key_id)
            row = conn.execute(stmt).fetchone()
            return self._row_to_record(row) if row else None

    def find_by_prefix(self, prefix: str) -> list[APIKeyRecord]:
        with self.engine.connect() as conn:
            stmt = select(self._table).where(self._table.c.prefix == prefix)
            rows = conn.execute(stmt).fetchall()
            return [self._row_to_record(r) for r in rows]

    def list_all(self) -> list[APIKeyRecord]:
        with self.engine.connect() as conn:
            stmt = select(self._table)
            rows = conn.execute(stmt).fetchall()
            return [self._row_to_record(r) for r in rows]

    def update_spend(self, key_id: str, additional_usd: float) -> APIKeyRecord:
        with self.engine.begin() as conn:
            stmt = select(self._table).where(self._table.c.key_id == key_id)
            row = conn.execute(stmt).fetchone()
            if not row:
                raise KeyError(f"API key '{key_id}' not found")

            new_spend = float(row.current_spend_usd or 0.0) + additional_usd
            update_stmt = (
                self._table.update()
                .where(self._table.c.key_id == key_id)
                .values(current_spend_usd=new_spend)
            )
            conn.execute(update_stmt)

            fetch_stmt = select(self._table).where(self._table.c.key_id == key_id)
            updated_row = conn.execute(fetch_stmt).fetchone()
            return self._row_to_record(updated_row)

    def revoke(self, key_id: str) -> bool:
        with self.engine.begin() as conn:
            check_stmt = select(self._table.c.key_id).where(self._table.c.key_id == key_id)
            if not conn.execute(check_stmt).fetchone():
                return False
            update_stmt = self._table.update().where(self._table.c.key_id == key_id).values(is_active=False)
            conn.execute(update_stmt)
            return True


class APIKeyService:
    """Service managing API key lifecycle, verification, USD caps, and rate limits."""

    def __init__(
        self,
        store: BaseAPIKeyStore | None = None,
        rate_limiter: FixedWindowRateLimiter | None = None,
        db_url: str | None = None,
    ) -> None:
        if store is not None:
            self.store = store
        elif db_url is not None:
            self.store = SQLAlchemyAPIKeyStore(db_url=db_url)
        elif os.environ.get("DB_URL") or os.environ.get("NEXCODER_DB_URL"):
            self.store = SQLAlchemyAPIKeyStore(db_url=os.environ.get("DB_URL") or os.environ["NEXCODER_DB_URL"])
        else:
            self.store = InMemoryAPIKeyStore()
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
