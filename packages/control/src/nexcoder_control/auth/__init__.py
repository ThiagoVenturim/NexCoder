"""Authentication subsystem: pluggable local, OIDC, and LDAP/AD authenticators."""

from nexcoder_control.auth.base import (
    AuthenticationError,
    AuthPrincipal,
    BaseAuthProvider,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
)
from nexcoder_control.auth.ldap import (
    BaseDirectoryProvider,
    DirectoryUser,
    InMemoryDirectoryProvider,
    LDAPAuthProvider,
    LDAPGroupMapping,
)
from nexcoder_control.auth.local import (
    LocalAuthProvider,
    LocalBearerToken,
    LocalUser,
)
from nexcoder_control.auth.oidc import (
    JWKSCache,
    MockOIDCProvider,
    OIDCAuthProvider,
    OIDCConfig,
)

__all__ = [
    "AuthenticationError",
    "AuthPrincipal",
    "BaseAuthProvider",
    "BaseDirectoryProvider",
    "DirectoryUser",
    "ForbiddenError",
    "InMemoryDirectoryProvider",
    "InvalidTokenError",
    "JWKSCache",
    "LDAPAuthProvider",
    "LDAPGroupMapping",
    "LocalAuthProvider",
    "LocalBearerToken",
    "LocalUser",
    "MockOIDCProvider",
    "OIDCAuthProvider",
    "OIDCConfig",
    "TokenExpiredError",
]
