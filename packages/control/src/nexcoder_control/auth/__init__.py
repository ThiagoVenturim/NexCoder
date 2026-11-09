"""Authentication subsystem: pluggable local, OIDC, and LDAP/AD authenticators."""

from faccoder_control.auth.base import (
    AuthenticationError,
    AuthPrincipal,
    BaseAuthProvider,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
)
from faccoder_control.auth.ldap import (
    BaseDirectoryProvider,
    DirectoryUser,
    InMemoryDirectoryProvider,
    LDAPAuthProvider,
    LDAPGroupMapping,
)
from faccoder_control.auth.local import (
    LocalAuthProvider,
    LocalBearerToken,
    LocalUser,
)
from faccoder_control.auth.oidc import (
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
