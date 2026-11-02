"""LDAP / Active Directory extensible interface and offline directory provider."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from faccoder_control.auth.base import (
    AuthenticationError,
    AuthPrincipal,
    BaseAuthProvider,
)


class DirectoryUser(BaseModel):
    """Directory user record from LDAP/Active Directory."""

    username: str
    full_name: str = ""
    email: str | None = None
    distinguished_name: str = ""
    groups: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class BaseDirectoryProvider(ABC):
    """Abstract interface for LDAP/Active Directory operations."""

    @abstractmethod
    def search_user(self, username: str) -> DirectoryUser | None:
        """Find a user by sAMAccountName / uid."""
        ...

    @abstractmethod
    def bind_authenticate(self, username: str, password: str) -> bool:
        """Perform simple bind or LDAP bind with user credentials."""
        ...

    @abstractmethod
    def get_user_groups(self, username: str) -> list[str]:
        """Fetch group DNs or common names for the user."""
        ...


@dataclass
class _DirectoryRecord:
    user: DirectoryUser
    password_hash: str
    salt: str


class InMemoryDirectoryProvider(BaseDirectoryProvider):
    """Offline test directory providing deterministic LDAP/Active Directory behavior."""

    def __init__(self) -> None:
        self._records: dict[str, _DirectoryRecord] = {}

    def add_user(
        self,
        username: str,
        password: str,
        full_name: str = "",
        email: str | None = None,
        groups: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        is_enabled: bool = True,
    ) -> DirectoryUser:
        clean_user = username.strip().lower()
        salt = secrets.token_bytes(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)

        user = DirectoryUser(
            username=clean_user,
            full_name=full_name or clean_user,
            email=email,
            distinguished_name=f"CN={clean_user},OU=Users,DC=corp,DC=local",
            groups=groups or ["Engineers"],
            attributes=attributes or {},
            is_enabled=is_enabled,
        )
        self._records[clean_user] = _DirectoryRecord(
            user=user,
            password_hash=key.hex(),
            salt=salt.hex(),
        )
        return user

    def search_user(self, username: str) -> DirectoryUser | None:
        clean = username.strip().lower()
        rec = self._records.get(clean)
        return rec.user if rec else None

    def bind_authenticate(self, username: str, password: str) -> bool:
        clean = username.strip().lower()
        rec = self._records.get(clean)
        if not rec or not rec.user.is_enabled:
            return False
        salt = bytes.fromhex(rec.salt)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()
        return hmac.compare_digest(computed, rec.password_hash)

    def get_user_groups(self, username: str) -> list[str]:
        user = self.search_user(username)
        return list(user.groups) if user else []


@dataclass
class LDAPGroupMapping:
    """Rules mapping LDAP/AD security groups to faccoder roles and scopes."""

    group_to_roles: dict[str, list[str]] = field(
        default_factory=lambda: {
            "CN=DevOps,OU=Groups,DC=corp,DC=local": ["admin"],
            "CN=Engineers,OU=Groups,DC=corp,DC=local": ["developer"],
            "Engineers": ["developer"],
            "DevOps": ["admin"],
        }
    )
    group_to_scopes: dict[str, list[str]] = field(
        default_factory=lambda: {
            "CN=DevOps,OU=Groups,DC=corp,DC=local": ["*"],
            "CN=Engineers,OU=Groups,DC=corp,DC=local": ["tools:execute", "metrics:read"],
            "Engineers": ["tools:execute", "metrics:read"],
            "DevOps": ["*"],
        }
    )


class LDAPAuthProvider(BaseAuthProvider):
    """LDAP and Active Directory authenticator with extensible directory provider."""

    def __init__(
        self,
        directory: BaseDirectoryProvider,
        mapping: LDAPGroupMapping | None = None,
        default_scopes: list[str] | None = None,
    ) -> None:
        self.directory = directory
        self.mapping = mapping or LDAPGroupMapping()
        self.default_scopes = default_scopes or ["tools:execute"]

    @property
    def provider_type(self) -> str:
        return "ldap"

    def authenticate_credentials(self, username: str, password: str) -> AuthPrincipal:
        clean_user = username.strip()
        if not clean_user or not password:
            raise AuthenticationError("Username and password cannot be empty")

        success = self.directory.bind_authenticate(clean_user, password)
        if not success:
            raise AuthenticationError("LDAP bind authentication failed")

        user = self.directory.search_user(clean_user)
        if not user or not user.is_enabled:
            raise AuthenticationError("User not found or disabled in directory")

        groups = self.directory.get_user_groups(clean_user)

        # Map groups to roles and scopes
        roles: set[str] = set()
        scopes: set[str] = set(self.default_scopes)

        for group in groups:
            if group in self.mapping.group_to_roles:
                roles.update(self.mapping.group_to_roles[group])
            if group in self.mapping.group_to_scopes:
                scopes.update(self.mapping.group_to_scopes[group])

        return AuthPrincipal(
            id=user.username,
            name=user.full_name or user.username,
            email=user.email,
            roles=sorted(roles),
            scopes=sorted(scopes),
            auth_type="ldap",
            is_active=user.is_enabled,
            metadata={
                "dn": user.distinguished_name,
                "groups": groups,
            },
        )

    def authenticate(self, credentials: Any) -> AuthPrincipal:
        if isinstance(credentials, dict):
            return self.authenticate_credentials(
                credentials.get("username", ""),
                credentials.get("password", ""),
            )
        if isinstance(credentials, (tuple, list)) and len(credentials) == 2:
            return self.authenticate_credentials(str(credentials[0]), str(credentials[1]))
        raise AuthenticationError("LDAP credentials must be dict with 'username' and 'password' or a 2-tuple")
