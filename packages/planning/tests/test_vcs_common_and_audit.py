"""Tests for VCS common base class, security token comparison, and audit logger."""

import pytest
from nexcoder_planning.vcs import (
    AuditRecord,
    RepoManagementProvider,
    UnsupportedCapabilityError,
    VCSAuditLogger,
    get_vcs_provider,
)


class DummyProvider(RepoManagementProvider):
    name = "dummy"
    capabilities = {"repositories", "issues"}


def test_secure_token_comparison():
    # Test constant-time token comparison against timing attacks
    secret = "secret-token-12345"
    assert RepoManagementProvider.secure_compare(secret, "secret-token-12345") is True
    assert RepoManagementProvider.secure_compare(secret, "secret-token-wrong") is False
    assert RepoManagementProvider.secure_compare(secret, "") is False
    assert RepoManagementProvider.secure_compare(secret, None) is False  # type: ignore[arg-type]


def test_load_secret_from_env(monkeypatch):
    monkeypatch.delenv("TEST_VCS_SECRET", raising=False)
    assert RepoManagementProvider.load_secret_from_env("TEST_VCS_SECRET") is None

    monkeypatch.setenv("TEST_VCS_SECRET", "  my-secret-val  ")
    assert RepoManagementProvider.load_secret_from_env("TEST_VCS_SECRET") == "my-secret-val"


def test_unsupported_capability_check():
    prov = DummyProvider()
    # repositories is supported, but pull_requests is not
    prov.check_capability("repositories")
    with pytest.raises(UnsupportedCapabilityError):
        prov.list_pull_requests()


def test_audit_logger_redaction():
    audit = VCSAuditLogger()
    rec = audit.record(
        provider="gitlab",
        action="create_issue",
        resource_type="issues",
        resource_id="101",
        success=True,
        details={
            "token": "sensitive-gl-token",
            "private_token": "secret-pat",
            "title": "Bug in login",
            "nested": {"password": "topsecret", "note": "safe-note"},
        },
    )

    assert isinstance(rec, AuditRecord)
    assert rec.details["token"] == "[REDACTED]"
    assert rec.details["private_token"] == "[REDACTED]"
    assert rec.details["title"] == "Bug in login"
    assert rec.details["nested"]["password"] == "[REDACTED]"
    assert rec.details["nested"]["note"] == "safe-note"

    records = audit.list_records(provider="gitlab")
    assert len(records) == 1
    assert records[0].resource_id == "101"


def test_factory_resolver():
    ado = get_vcs_provider("azure_devops", organization="myorg", project="myproj", pat="p")
    assert ado.name == "azure_devops"

    gl = get_vcs_provider("gitlab", project_id=123, token="t")
    assert gl.name == "gitlab"

    git = get_vcs_provider("git")
    assert git.name == "git"

    svn = get_vcs_provider("svn")
    assert svn.name == "svn"

    tgit = get_vcs_provider("tortoise_git")
    assert tgit.name == "tortoise_git"

    with pytest.raises(ValueError, match="Unknown VCS provider"):
        get_vcs_provider("unknown_provider")
