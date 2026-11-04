"""Local authentication provider supporting username/password and bearer tokens with scopes."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from faccoder_control.auth.base import (
    AuthenticationError,
    AuthPrincipal,
    BaseAuthProvider,
    TokenExpiredError,
)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return key.hex(), salt.hex()


def verify_password(password: str, hashed_hex: str, salt_hex: str) -> bool:
    """Verify password against hashed value in constant time."""
    salt = bytes.fromhex(salt_hex)
    computed_hex, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hex, hashed_hex)


@dataclass
class LocalUser:
    username: str
    password_hash: str
    password_salt: str
    full_name: str = ""
    email: str | None = None
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalBearerToken:
    token_hash: str
    user_id: str
    scopes: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    is_revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class LocalAuthProvider(BaseAuthProvider):
    """Local authenticator for users, passwords, and bearer tokens."""

    def __init__(self) -> None:
        self._users: dict[str, LocalUser] = {}
        self._tokens: dict[str, LocalBearerToken] = {}  # token_hash -> token record

    @property
    def provider_type(self) -> str:
        return "local"

    def register_user(
        self,
        username: str,
        password: str,
        full_name: str = "",
        email: str | None = None,
        roles: list[str] | None = None,
        scopes: list[str] | None = None,
    ) -> LocalUser:
        """Register a new local user with hashed credentials."""
        clean_user = username.strip().lower()
        if not clean_user:
            raise ValueError("Username cannot be empty")
        pwd_hash, salt = hash_password(password)
        user = LocalUser(
            username=clean_user,
            password_hash=pwd_hash,
            password_salt=salt,
            full_name=full_name or clean_user,
            email=email,
            roles=roles or ["user"],
            scopes=scopes or ["tools:execute", "metrics:read"],
        )
        self._users[clean_user] = user
        return user

    def authenticate_credentials(self, username: str, password: str) -> AuthPrincipal:
        """Authenticate username and password against local registry."""
        clean_user = username.strip().lower()
        user = self._users.get(clean_user)
        if not user or not user.is_active:
            raise AuthenticationError("Invalid username or password")
        if not verify_password(password, user.password_hash, user.password_salt):
            raise AuthenticationError("Invalid username or password")
        return AuthPrincipal(
            id=user.username,
            name=user.full_name,
            email=user.email,
            roles=list(user.roles),
            scopes=list(user.scopes),
            auth_type="local_password",
            is_active=user.is_active,
            is_human=True,
            metadata=dict(user.metadata),
        )

    def issue_bearer_token(
        self,
        username: str,
        scopes: list[str] | None = None,
        roles: list[str] | None = None,
        ttl_minutes: int | None = 60,
    ) -> str:
        """Issue a random high-entropy bearer token for a user and return the raw secret."""
        clean_user = username.strip().lower()
        user = self._users.get(clean_user)
        user_roles = roles if roles is not None else (user.roles if user else ["user"])
        user_scopes = scopes if scopes is not None else (user.scopes if user else ["tools:execute"])

        raw_secret = f"fc_bearer_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl_minutes) if ttl_minutes else None

        record = LocalBearerToken(
            token_hash=token_hash,
            user_id=clean_user,
            scopes=list(user_scopes),
            roles=list(user_roles),
            created_at=now,
            expires_at=expires_at,
        )
        self._tokens[token_hash] = record
        return raw_secret

    def authenticate_bearer_token(self, raw_token: str) -> AuthPrincipal:
        """Verify bearer token in constant time."""
        clean_token = raw_token.strip()
        if not clean_token:
            raise AuthenticationError("Bearer token cannot be empty")
        token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()

        # Constant-time lookup match
        match: LocalBearerToken | None = None
        for stored_hash, record in self._tokens.items():
            if hmac.compare_digest(stored_hash, token_hash):
                match = record
                break

        if not match or match.is_revoked:
            raise AuthenticationError("Invalid or revoked bearer token")

        if match.expires_at and datetime.now(UTC) > match.expires_at:
            raise TokenExpiredError("Bearer token has expired")

        user = self._users.get(match.user_id)
        name = user.full_name if user else match.user_id
        email = user.email if user else None

        return AuthPrincipal(
            id=match.user_id,
            name=name,
            email=email,
            roles=list(match.roles),
            scopes=list(match.scopes),
            auth_type="local_bearer",
            is_active=user.is_active if user else True,
            is_human=True,
            metadata={"token_created_at": match.created_at.isoformat()},
        )

    def revoke_token(self, raw_token: str) -> bool:
        """Revoke a previously issued bearer token."""
        token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
        for stored_hash, record in self._tokens.items():
            if hmac.compare_digest(stored_hash, token_hash):
                record.is_revoked = True
                return True
        return False

    def authenticate(self, credentials: Any) -> AuthPrincipal:
        """Dispatch credentials by shape: dictionary or raw bearer token string."""
        if isinstance(credentials, dict):
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            return self.authenticate_credentials(username, password)
        if isinstance(credentials, str):
            return self.authenticate_bearer_token(credentials)
        raise AuthenticationError("Unsupported credentials format")
