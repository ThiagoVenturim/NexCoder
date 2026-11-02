"""Base authentication models, interfaces, and exceptions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AuthenticationError(Exception):
    """Raised when authentication fails (HTTP 401 equivalent)."""

    def __init__(self, message: str = "Authentication failed", status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ForbiddenError(Exception):
    """Raised when an authenticated principal lacks required scope or permissions (HTTP 403 equivalent)."""

    def __init__(self, message: str = "Insufficient permissions", status_code: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TokenExpiredError(AuthenticationError):
    """Raised when a presented token has expired."""

    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message=message, status_code=401)


class InvalidTokenError(AuthenticationError):
    """Raised when a presented token is malformed or invalid."""

    def __init__(self, message: str = "Invalid token") -> None:
        super().__init__(message=message, status_code=401)


class AuthPrincipal(BaseModel):
    """Authenticated subject identity."""

    id: str
    name: str = ""
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    auth_type: str = "unknown"
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_scope(self, required_scope: str) -> bool:
        """Check if principal holds a required scope (supports wildcard '*' and namespace:*)."""
        if not self.is_active:
            return False
        if "*" in self.scopes or "admin" in self.roles:
            return True
        if required_scope in self.scopes:
            return True
        # Check namespace wildcard e.g. "tools:*" matches "tools:read"
        if ":" in required_scope:
            namespace = required_scope.split(":", 1)[0]
            if f"{namespace}:*" in self.scopes:
                return True
        return False

    def require_scope(self, required_scope: str) -> None:
        """Raise ForbiddenError if required scope is missing."""
        if not self.has_scope(required_scope):
            raise ForbiddenError(f"Principal '{self.id}' lacks required scope '{required_scope}'")

    def has_role(self, role: str) -> bool:
        """Check if principal possesses a specific role."""
        if not self.is_active:
            return False
        return role in self.roles or "admin" in self.roles


class BaseAuthProvider(ABC):
    """Abstract pluggable authentication provider interface."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Name of provider type (e.g. 'local', 'oidc', 'ldap')."""
        ...

    @abstractmethod
    def authenticate(self, credentials: Any) -> AuthPrincipal | None:
        """Authenticate presented credentials and return AuthPrincipal on success, or None/raise on failure."""
        ...
