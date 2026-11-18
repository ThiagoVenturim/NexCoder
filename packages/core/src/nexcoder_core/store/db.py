"""Pluggable database layer: SQLAlchemy engine management and unified schema.

Supports SQLite by default (zero configuration) and any SQLAlchemy-supported
external database (PostgreSQL, MySQL, SQL Server via ODBC) specified via DB_URL.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine

DEFAULT_SQLITE_URL = "sqlite:///.nexcoder/nexcoder.db"


def get_db_url(default: str | None = None) -> str:
    """Resolve active database URL from environment or fallback default."""
    if default:
        return default
    return (
        os.environ.get("DB_URL")
        or os.environ.get("NEXCODER_DB_URL")
        or DEFAULT_SQLITE_URL
    )


def normalize_db_url(url: str) -> str:
    """Normalize database connection string for SQLAlchemy engine compatibility.

    Supports:
    - Standard SQLAlchemy URLs (sqlite:///, postgresql://, mysql+pymysql://, etc.)
    - Legacy postgres:// schema mapped to postgresql://
    - ODBC connection strings (e.g. Driver={ODBC Driver...};Server=...;Database=...)
    """
    clean_url = url.strip()

    # PostgreSQL legacy URL mapping
    if clean_url.startswith("postgres://"):
        return "postgresql://" + clean_url[len("postgres://") :]

    # Raw ODBC connection string for SQL Server / ODBC
    if clean_url.lower().startswith("driver={") or "server=" in clean_url.lower():
        encoded = urllib.parse.quote_plus(clean_url)
        return f"mssql+pyodbc:///?odbc_connect={encoded}"

    if clean_url.lower().startswith("odbc://"):
        raw_odbc = clean_url[len("odbc://") :]
        encoded = urllib.parse.quote_plus(raw_odbc)
        return f"mssql+pyodbc:///?odbc_connect={encoded}"

    return clean_url


def create_db_engine(db_url: str | None = None, **kwargs: Any) -> Engine:
    """Create a configured SQLAlchemy engine with appropriate dialect defaults."""
    resolved_url = normalize_db_url(get_db_url(db_url))

    engine_kwargs: dict[str, Any] = dict(kwargs)

    if resolved_url.startswith("sqlite"):
        # SQLite multi-threading support
        connect_args = dict(engine_kwargs.get("connect_args", {}))
        connect_args.setdefault("check_same_thread", False)
        engine_kwargs["connect_args"] = connect_args
        # Create local directory if path points to a file
        if resolved_url.startswith("sqlite:///") and not resolved_url.startswith("sqlite:///:memory:"):
            db_path = resolved_url[len("sqlite:///") :]
            # Handle Windows paths or relative paths
            cleaned_path = db_path.split("?")[0]
            if cleaned_path and not cleaned_path.startswith(":"):
                Path(cleaned_path).parent.mkdir(parents=True, exist_ok=True)
    else:
        # Connection pooling ping for external databases
        engine_kwargs.setdefault("pool_pre_ping", True)

    return create_engine(resolved_url, **engine_kwargs)


def get_metadata() -> MetaData:
    """Return unified SQLAlchemy metadata defining core and control plane tables."""
    metadata = MetaData()

    # Core: Chunks for hybrid search and vector index
    Table(
        "chunks",
        metadata,
        Column("id", String(255), primary_key=True),
        Column("text", Text, nullable=False),
        Column("metadata_json", Text, nullable=False, default="{}"),
        Column("content_hash", String(64), nullable=True),
        Column("embedding", LargeBinary, nullable=True),
    )

    # Core: Index metadata (e.g. vector dimensions)
    Table(
        "meta",
        metadata,
        Column("key", String(128), primary_key=True),
        Column("value", Text, nullable=False),
    )

    # Control: Append-only cryptographic audit events
    Table(
        "audit_events",
        metadata,
        Column("event_id", String(64), primary_key=True),
        Column("sequence_no", Integer, nullable=False),
        Column("timestamp", DateTime(timezone=True), nullable=False),
        Column("event_type", String(128), nullable=False),
        Column("actor", String(255), nullable=False),
        Column("action", String(128), nullable=False),
        Column("resource", String(512), nullable=False),
        Column("severity", String(32), nullable=False, default="info"),
        Column("prev_hash", String(64), nullable=False),
        Column("event_hash", String(64), nullable=False),
        Column("details_json", Text, nullable=False, default="{}"),
    )

    # Control: API Key storage
    Table(
        "api_keys",
        metadata,
        Column("key_id", String(64), primary_key=True),
        Column("name", String(255), nullable=False),
        Column("prefix", String(32), nullable=False),
        Column("hashed_secret", String(128), nullable=False),
        Column("owner", String(255), nullable=False),
        Column("tier", String(32), nullable=False, default="standard"),
        Column("is_active", Boolean, nullable=False, default=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=True),
        Column("current_spend_usd", Float, nullable=False, default=0.0),
        Column("budget_limit_usd", Float, nullable=True),
        Column("rate_limit_rpm", Integer, nullable=False, default=60),
        Column("allowed_models", Text, nullable=False, default="[]"),
        Column("allowed_endpoints", Text, nullable=False, default="[]"),
        Column("metadata_json", Text, nullable=False, default="{}"),
    )

    return metadata


def init_db(engine: Engine | None = None, db_url: str | None = None) -> Engine:
    """Initialize database tables according to unified schema metadata."""
    target_engine = engine or create_db_engine(db_url)
    metadata = get_metadata()
    metadata.create_all(target_engine)
    return target_engine
