"""Pytest fixtures for nexcoder-control tests."""

from __future__ import annotations

import pytest
from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.approval.tokens import ApprovalTokenManager
from nexcoder_control.auth.ldap import InMemoryDirectoryProvider, LDAPAuthProvider
from nexcoder_control.auth.local import LocalAuthProvider
from nexcoder_control.auth.oidc import MockOIDCProvider, OIDCAuthProvider, OIDCConfig
from nexcoder_control.keys.store import APIKeyService, InMemoryAPIKeyStore
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_control.metering.mcp_middleware import MCPToolMeter


@pytest.fixture
def local_auth() -> LocalAuthProvider:
    provider = LocalAuthProvider()
    provider.register_user(
        username="alice",
        password="SecretPassword123!",
        full_name="Alice Engineer",
        email="alice@example.com",
        roles=["developer"],
        scopes=["tools:execute", "metrics:read"],
    )
    return provider


@pytest.fixture
def mock_oidc() -> tuple[MockOIDCProvider, OIDCAuthProvider]:
    mock_idp = MockOIDCProvider(
        issuer="https://auth.example.com",
        audience="test-client-id",
    )
    config = OIDCConfig(
        issuer=mock_idp.issuer,
        audience=mock_idp.audience,
    )
    auth_provider = OIDCAuthProvider(
        config=config,
        jwks_provider=mock_idp.get_jwks,
    )
    return mock_idp, auth_provider


@pytest.fixture
def ldap_auth() -> LDAPAuthProvider:
    dir_provider = InMemoryDirectoryProvider()
    dir_provider.add_user(
        username="bob",
        password="LdapPassword456!",
        full_name="Bob Admin",
        email="bob@example.com",
        groups=["DevOps"],
    )
    return LDAPAuthProvider(directory=dir_provider)


@pytest.fixture
def key_service() -> APIKeyService:
    store = InMemoryAPIKeyStore()
    return APIKeyService(store=store)


@pytest.fixture
def tool_meter() -> MCPToolMeter:
    return MCPToolMeter(default_model="gpt-4.1-mini")


@pytest.fixture
def cost_tracker() -> CostTracker:
    return CostTracker()


@pytest.fixture
def budget_manager(cost_tracker: CostTracker) -> BudgetManager:
    return BudgetManager(cost_tracker)


@pytest.fixture
def audit_log() -> AppendOnlyAuditLog:
    return AppendOnlyAuditLog()


@pytest.fixture
def approval_manager() -> ApprovalTokenManager:
    return ApprovalTokenManager()


@pytest.fixture
def machine_manager() -> MachineApprovalManager:
    return MachineApprovalManager()
