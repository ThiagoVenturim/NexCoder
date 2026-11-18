"""Tests for VCS tools and CLI subcommands."""

from unittest.mock import patch

from nexcoder_interfaces.cli.main import app
from nexcoder_interfaces.tools.vcs import (
    vcs_audit_records,
    vcs_list_repositories,
    vcs_manage_issue,
    vcs_manage_pull_request,
    vcs_svn_operation,
)
from nexcoder_planning.vcs.models import IssueItem, PullRequestItem, RepoItem, VCSCommit
from typer.testing import CliRunner

runner = CliRunner()


def test_vcs_list_repositories_tool():
    with patch("nexcoder_planning.vcs.GitLabProvider.list_repositories") as mock_list:
        mock_list.return_value = [
            RepoItem(
                id="123",
                name="service-a",
                web_url="https://gitlab.com/group/service-a",
            )
        ]
        res = vcs_list_repositories(provider="gitlab", project_or_org="123", token="gl-tok")
        assert res["status"] == "success"
        assert res["count"] == 1
        assert res["repositories"][0]["name"] == "service-a"


def test_vcs_manage_issue_tool():
    with patch("nexcoder_planning.vcs.AzureDevOpsProvider.create_issue") as mock_create:
        mock_create.return_value = IssueItem(
            id="405",
            number=405,
            title="Fix bug",
            body="Details",
            state="open",
        )
        res = vcs_manage_issue(
            provider="azure_devops",
            action="create",
            project_or_org="myorg",
            project="myproj",
            title="Fix bug",
            body="Details",
            token="pat-token",
        )
        assert res["status"] == "success"
        assert res["action"] == "create"
        assert res["issue"]["id"] == "405"


def test_vcs_manage_pull_request_tool():
    with patch("nexcoder_planning.vcs.GitLabProvider.create_pull_request") as mock_pr:
        mock_pr.return_value = PullRequestItem(
            id="99",
            number=99,
            title="feat: new module",
            source_branch="feat/new",
            target_branch="develop",
            state="open",
        )
        res = vcs_manage_pull_request(
            provider="gitlab",
            action="create",
            project_or_org="123",
            title="feat: new module",
            body="MR body",
            source_branch="feat/new",
            target_branch="develop",
            token="gl-tok",
        )
        assert res["status"] == "success"
        assert res["pull_request"]["number"] == 99


def test_vcs_svn_operation_tool():
    with patch("nexcoder_planning.vcs.SVNProvider.commit") as mock_commit:
        mock_commit.return_value = VCSCommit(
            revision="5",
            message="feat: new feature",
        )
        res = vcs_svn_operation(action="commit", message="feat: new feature")
        assert res["status"] == "success"
        assert res["commit"]["revision"] == "5"


def test_vcs_audit_records_tool():
    res = vcs_audit_records(limit=10)
    assert res["status"] == "success"
    assert "records" in res


def test_vcs_cli_subcommands():
    # Test vcs tortoise command
    res = runner.invoke(app, ["vcs", "tortoise", "--command", "commit", "--path", "."])
    assert res.exit_code == 0
    assert "TortoiseGit Installed:" in res.stdout
    assert "/command:commit" in res.stdout

    # Test vcs audit command
    res_audit = runner.invoke(app, ["vcs", "audit", "--limit", "5"])
    assert res_audit.exit_code == 0
    assert "Audit Records" in res_audit.stdout
