"""Tests for authentication subsystem: Local, OIDC, and LDAP/AD."""

from __future__ import annotations

import pytest
from faccoder_control.auth.base import (
    AuthenticationError,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
)
from faccoder_control.auth.ldap import LDAPAuthProvider
from faccoder_control.auth.local import LocalAuthProvider
from faccoder_control.auth.oidc import MockOIDCProvider, OIDCAuthProvider


class TestLocalAuth:
    def test_authenticate_success(self, local_auth: LocalAuthProvider) -> None:
        principal = local_auth.authenticate({"username": "alice", "password": "SecretPassword123!"})
        assert principal.id == "alice"
        assert principal.name == "Alice Engineer"
        assert principal.email == "alice@example.com"
        assert "developer" in principal.roles
        assert principal.has_scope("tools:execute")
        assert principal.has_scope("metrics:read")
        assert not principal.has_scope("admin:write")

    def test_authenticate_wrong_password(self, local_auth: LocalAuthProvider) -> None:
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            local_auth.authenticate({"username": "alice", "password": "WrongPassword"})

    def test_authenticate_nonexistent_user(self, local_auth: LocalAuthProvider) -> None:
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            local_auth.authenticate({"username": "ghost", "password": "SecretPassword123!"})

    def test_bearer_token_issue_and_verify(self, local_auth: LocalAuthProvider) -> None:
        token = local_auth.issue_bearer_token("alice", scopes=["tools:execute"], ttl_minutes=30)
        assert token.startswith("fc_bearer_")

        principal = local_auth.authenticate(token)
        assert principal.id == "alice"
        assert principal.has_scope("tools:execute")

    def test_bearer_token_revocation(self, local_auth: LocalAuthProvider) -> None:
        token = local_auth.issue_bearer_token("alice", ttl_minutes=30)
        assert local_auth.revoke_token(token) is True

        with pytest.raises(AuthenticationError, match="Invalid or revoked bearer token"):
            local_auth.authenticate(token)

    def test_bearer_token_expired(self, local_auth: LocalAuthProvider) -> None:
        token = local_auth.issue_bearer_token("alice", ttl_minutes=-5)
        with pytest.raises(TokenExpiredError):
            local_auth.authenticate(token)

    def test_principal_require_scope(self, local_auth: LocalAuthProvider) -> None:
        principal = local_auth.authenticate({"username": "alice", "password": "SecretPassword123!"})
        principal.require_scope("tools:execute")
        with pytest.raises(ForbiddenError, match="lacks required scope"):
            principal.require_scope("financial:write")


class TestOIDCAuth:
    def test_verify_valid_token(self, mock_oidc: tuple[MockOIDCProvider, OIDCAuthProvider]) -> None:
        mock_idp, oidc_auth = mock_oidc
        token = mock_idp.mint_token(
            subject="usr_42",
            name="Charlie Engineer",
            email="charlie@example.com",
            scopes=["tools:execute", "pipelines:run"],
            roles=["developer"],
        )
        principal = oidc_auth.authenticate(token)
        assert principal.id == "usr_42"
        assert principal.name == "Charlie Engineer"
        assert principal.email == "charlie@example.com"
        assert principal.auth_type == "oidc"
        assert principal.has_scope("pipelines:run")

    def test_verify_expired_token(self, mock_oidc: tuple[MockOIDCProvider, OIDCAuthProvider]) -> None:
        mock_idp, oidc_auth = mock_oidc
        expired_token = mock_idp.mint_token(expired=True)
        with pytest.raises(TokenExpiredError):
            oidc_auth.authenticate(expired_token)

    def test_verify_audience_mismatch(self, mock_oidc: tuple[MockOIDCProvider, OIDCAuthProvider]) -> None:
        mock_idp, oidc_auth = mock_oidc
        token = mock_idp.mint_token(audience="wrong-client-id")
        with pytest.raises(InvalidTokenError):
            oidc_auth.authenticate(token)

    def test_verify_issuer_mismatch(self, mock_oidc: tuple[MockOIDCProvider, OIDCAuthProvider]) -> None:
        mock_idp, oidc_auth = mock_oidc
        token = mock_idp.mint_token(issuer="https://untrusted-issuer.org")
        with pytest.raises(InvalidTokenError):
            oidc_auth.authenticate(token)

    def test_algorithm_confusion_attack_rejected(self, mock_oidc: tuple[MockOIDCProvider, OIDCAuthProvider]) -> None:
        import base64
        import hashlib
        import hmac
        import json
        from datetime import UTC, datetime

        mock_idp, oidc_auth = mock_oidc

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

        header = {"alg": "HS256", "typ": "JWT", "kid": mock_idp.key_id}
        payload = {
            "iss": mock_idp.issuer,
            "aud": mock_idp.audience,
            "sub": "attacker",
            "exp": int(datetime.now(UTC).timestamp()) + 3600,
            "iat": int(datetime.now(UTC).timestamp()),
        }
        signing_input = f"{b64url(json.dumps(header).encode('utf-8'))}.{b64url(json.dumps(payload).encode('utf-8'))}"
        sig = hmac.new(mock_idp._public_pem.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        confusion_token = f"{signing_input}.{b64url(sig)}"

        with pytest.raises(InvalidTokenError, match="algorithm 'HS256'"):
            oidc_auth.authenticate(confusion_token)


class TestLDAPAuth:
    def test_ldap_authenticate_success(self, ldap_auth: LDAPAuthProvider) -> None:
        principal = ldap_auth.authenticate({"username": "bob", "password": "LdapPassword456!"})
        assert principal.id == "bob"
        assert principal.name == "Bob Admin"
        assert principal.auth_type == "ldap"
        assert "admin" in principal.roles
        assert principal.has_scope("*")

    def test_ldap_wrong_password(self, ldap_auth: LDAPAuthProvider) -> None:
        with pytest.raises(AuthenticationError, match="LDAP bind authentication failed"):
            ldap_auth.authenticate({"username": "bob", "password": "BadPassword"})

    def test_ldap_user_not_found(self, ldap_auth: LDAPAuthProvider) -> None:
        with pytest.raises(AuthenticationError):
            ldap_auth.authenticate({"username": "unknown_user", "password": "AnyPassword"})
