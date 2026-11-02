"""OIDC authenticator with JWKS caching and deterministic offline mock provider."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from faccoder_control.auth.base import (
    AuthenticationError,
    AuthPrincipal,
    BaseAuthProvider,
    InvalidTokenError,
    TokenExpiredError,
)


@dataclass
class JWKSCacheEntry:
    keys: dict[str, Any]  # kid -> public key pem or dict
    expires_at: float


class JWKSCache:
    """In-memory time-to-live cache for JWKS keys."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, JWKSCacheEntry] = {}

    def get(self, issuer: str) -> dict[str, Any] | None:
        entry = self._cache.get(issuer)
        if not entry:
            return None
        if time.time() > entry.expires_at:
            del self._cache[issuer]
            return None
        return entry.keys

    def set(self, issuer: str, keys: dict[str, Any]) -> None:
        self._cache[issuer] = JWKSCacheEntry(
            keys=keys,
            expires_at=time.time() + self.ttl_seconds,
        )

    def clear(self) -> None:
        self._cache.clear()


@dataclass
class OIDCConfig:
    issuer: str
    audience: str
    jwks_uri: str | None = None
    algorithms: list[str] = field(default_factory=lambda: ["RS256", "HS256"])
    jwks_cache_ttl_seconds: int = 3600
    clock_skew_seconds: int = 30


class OIDCAuthProvider(BaseAuthProvider):
    """OpenID Connect authenticator with JWKS caching and offline mock support."""

    def __init__(
        self,
        config: OIDCConfig,
        jwks_cache: JWKSCache | None = None,
        jwks_provider: Any = None,
    ) -> None:
        self.config = config
        self.cache = jwks_cache or JWKSCache(ttl_seconds=config.jwks_cache_ttl_seconds)
        self.jwks_provider = jwks_provider  # Callable or dict returning JWKS in offline/mock mode

    @property
    def provider_type(self) -> str:
        return "oidc"

    def _get_key(self, kid: str | None, algorithm: str) -> Any:
        """Resolve public key for the kid from cache, jwks_provider or static map."""
        cached_keys = self.cache.get(self.config.issuer)
        if cached_keys is None:
            if callable(self.jwks_provider):
                cached_keys = self.jwks_provider()
            elif isinstance(self.jwks_provider, dict):
                cached_keys = self.jwks_provider
            else:
                cached_keys = {}
            self.cache.set(self.config.issuer, cached_keys)

        if not cached_keys:
            raise AuthenticationError(f"No JWKS keys available for issuer {self.config.issuer}")

        if kid:
            if kid not in cached_keys:
                # Invalidate cache and retry once if callable
                if callable(self.jwks_provider):
                    cached_keys = self.jwks_provider()
                    self.cache.set(self.config.issuer, cached_keys)
                if kid not in cached_keys:
                    raise InvalidTokenError(f"Signing key kid '{kid}' not found in JWKS")
            return cached_keys[kid]

        # If no kid specified, fallback to default/first key
        if len(cached_keys) == 1:
            return next(iter(cached_keys.values()))
        raise InvalidTokenError("Token header lacks 'kid' and multiple keys are configured")

    def verify_token(self, token: str) -> AuthPrincipal:
        """Verify JWT signature, issuer, audience, and exp offline using cached JWKS."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise InvalidTokenError(f"Malformed JWT header: {exc}") from exc

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")
        if alg not in self.config.algorithms:
            raise InvalidTokenError(f"Unsupported algorithm '{alg}', allowed: {self.config.algorithms}")

        key = self._get_key(kid, alg)

        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                audience=self.config.audience,
                issuer=self.config.issuer,
                leeway=self.config.clock_skew_seconds,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("OIDC token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"OIDC token verification failed: {exc}") from exc

        sub = payload.get("sub", "")
        if not sub:
            raise InvalidTokenError("OIDC token payload missing 'sub' subject claim")

        # Parse scopes from standard scope claim or scp claim
        scopes: list[str] = []
        raw_scope = payload.get("scope") or payload.get("scp")
        if isinstance(raw_scope, str):
            scopes = raw_scope.split()
        elif isinstance(raw_scope, list):
            scopes = [str(s) for s in raw_scope]

        roles: list[str] = []
        raw_roles = payload.get("roles") or payload.get("groups") or []
        if isinstance(raw_roles, list):
            roles = [str(r) for r in raw_roles]
        elif isinstance(raw_roles, str):
            roles = [raw_roles]

        return AuthPrincipal(
            id=sub,
            name=payload.get("name") or payload.get("preferred_username") or sub,
            email=payload.get("email"),
            roles=roles,
            scopes=scopes,
            auth_type="oidc",
            is_active=True,
            metadata={
                "iss": payload.get("iss"),
                "aud": payload.get("aud"),
                "jti": payload.get("jti"),
            },
        )

    def authenticate(self, credentials: Any) -> AuthPrincipal:
        """Authenticate bearer token string."""
        if not isinstance(credentials, str):
            raise AuthenticationError("OIDC credentials must be a raw JWT string")
        return self.verify_token(credentials.strip())


class MockOIDCProvider:
    """Deterministic offline OIDC identity provider generating keys and signed tokens for tests."""

    def __init__(
        self,
        issuer: str = "https://auth.faccoder.local/oauth2",
        audience: str = "faccoder-api",
        key_id: str = "mock-key-1",
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.key_id = key_id

        # Generate standard RSA keypair
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()

        self._public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        self._private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    def get_jwks(self) -> dict[str, str]:
        """Return mapping of kid to PEM-encoded public key for JWKS verification."""
        return {self.key_id: self._public_pem}

    def mint_token(
        self,
        subject: str = "usr_mock123",
        name: str = "Mock Engineer",
        email: str = "engineer@example.com",
        scopes: list[str] | None = None,
        roles: list[str] | None = None,
        ttl_seconds: int = 3600,
        expired: bool = False,
        issuer: str | None = None,
        audience: str | None = None,
    ) -> str:
        """Generate signed RS256 JWT token."""
        now = datetime.now(UTC)
        if expired:
            exp = now - timedelta(seconds=60)
            iat = now - timedelta(seconds=3600)
        else:
            exp = now + timedelta(seconds=ttl_seconds)
            iat = now

        payload = {
            "iss": issuer or self.issuer,
            "aud": audience or self.audience,
            "sub": subject,
            "name": name,
            "email": email,
            "scope": " ".join(scopes or ["tools:execute", "metrics:read"]),
            "roles": roles or ["developer"],
            "iat": int(iat.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": f"mock_jti_{int(now.timestamp())}",
        }

        token = jwt.encode(
            payload,
            self._private_pem,
            algorithm="RS256",
            headers={"kid": self.key_id},
        )
        return token
