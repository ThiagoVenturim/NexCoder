"""VCS and repository management tools for NexCoder agents and MCP interfaces."""

from __future__ import annotations

from typing import Any


def vcs_list_repositories(
    provider: str = "gitlab",
    project_or_org: str = "",
    project: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """List repositories from Azure DevOps, GitLab, or Git."""
    try:
        from nexcoder_planning.vcs import get_vcs_provider

        kwargs: dict[str, Any] = {}
        if provider == "azure_devops":
            kwargs["organization"] = project_or_org
            kwargs["project"] = project
            if token:
                kwargs["pat"] = token
        elif provider == "gitlab":
            kwargs["project_id"] = project_or_org or project
            if token:
                kwargs["token"] = token

        prov = get_vcs_provider(provider, **kwargs)
        repos = prov.list_repositories()
        return {
            "status": "success",
            "provider": provider,
            "count": len(repos),
            "repositories": [r.model_dump() for r in repos],
        }
    except Exception as exc:
        return {"status": "error", "provider": provider, "message": str(exc)}


def vcs_manage_issue(
    provider: str,
    action: str = "list",
    project_or_org: str = "",
    project: str = "",
    issue_id: str = "",
    title: str = "",
    body: str = "",
    state: str = "open",
    labels: list[str] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create, read, update, or list issues on Azure DevOps or GitLab."""
    try:
        from nexcoder_planning.vcs import get_vcs_provider

        kwargs: dict[str, Any] = {}
        if provider == "azure_devops":
            kwargs["organization"] = project_or_org
            kwargs["project"] = project
            if token:
                kwargs["pat"] = token
        elif provider == "gitlab":
            kwargs["project_id"] = project_or_org or project
            if token:
                kwargs["token"] = token

        prov = get_vcs_provider(provider, **kwargs)

        if action == "list":
            issues = prov.list_issues(state=state)
            return {
                "status": "success",
                "action": "list",
                "count": len(issues),
                "issues": [i.model_dump() for i in issues],
            }
        elif action == "get":
            issue = prov.get_issue(issue_id)
            return {"status": "success", "action": "get", "issue": issue.model_dump()}
        elif action == "create":
            created = prov.create_issue(title=title, body=body, labels=labels)
            return {"status": "success", "action": "create", "issue": created.model_dump()}
        elif action == "update":
            updated = prov.update_issue(
                issue_id=issue_id,
                title=title or None,
                body=body or None,
                state=state or None,
                labels=labels,
            )
            return {"status": "success", "action": "update", "issue": updated.model_dump()}
        else:
            return {"status": "error", "message": f"Unsupported action '{action}'"}
    except Exception as exc:
        return {"status": "error", "provider": provider, "action": action, "message": str(exc)}


def vcs_manage_pull_request(
    provider: str,
    action: str = "list",
    project_or_org: str = "",
    project: str = "",
    pr_id: str = "",
    title: str = "",
    body: str = "",
    source_branch: str = "",
    target_branch: str = "develop",
    commit_message: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """Create, read, list, or merge pull requests/merge requests on Azure DevOps or GitLab."""
    try:
        from nexcoder_planning.vcs import get_vcs_provider

        kwargs: dict[str, Any] = {}
        if provider == "azure_devops":
            kwargs["organization"] = project_or_org
            kwargs["project"] = project
            if token:
                kwargs["pat"] = token
        elif provider == "gitlab":
            kwargs["project_id"] = project_or_org or project
            if token:
                kwargs["token"] = token

        prov = get_vcs_provider(provider, **kwargs)

        if action == "list":
            prs = prov.list_pull_requests()
            return {
                "status": "success",
                "action": "list",
                "count": len(prs),
                "pull_requests": [p.model_dump() for p in prs],
            }
        elif action == "get":
            pr = prov.get_pull_request(pr_id)
            return {"status": "success", "action": "get", "pull_request": pr.model_dump()}
        elif action == "create":
            created = prov.create_pull_request(
                title=title,
                body=body,
                source_branch=source_branch,
                target_branch=target_branch,
            )
            return {"status": "success", "action": "create", "pull_request": created.model_dump()}
        elif action == "merge":
            merged = prov.merge_pull_request(pr_id=pr_id, commit_message=commit_message)
            return {"status": "success", "action": "merge", "pull_request": merged.model_dump()}
        else:
            return {"status": "error", "message": f"Unsupported action '{action}'"}
    except Exception as exc:
        return {"status": "error", "provider": provider, "action": action, "message": str(exc)}


def vcs_svn_operation(
    action: str,
    repo_url: str = "",
    dest_path: str = "",
    message: str = "",
    files: list[str] | None = None,
    limit: int = 10,
    revision: str = "HEAD",
) -> dict[str, Any]:
    """Execute high-level Subversion operations (checkout, commit, log, diff, status)."""
    try:
        from nexcoder_planning.vcs import SVNProvider

        prov = SVNProvider(working_dir=dest_path or None)
        if action == "checkout":
            prov.checkout(repo_url=repo_url, dest_path=dest_path or None, revision=revision)
            return {"status": "success", "action": "checkout", "dest": dest_path}
        elif action == "commit":
            commit = prov.commit(message=message, files=files)
            return {"status": "success", "action": "commit", "commit": commit.model_dump()}
        elif action == "log":
            logs = prov.get_log(limit=limit)
            return {"status": "success", "action": "log", "entries": [e.model_dump() for e in logs]}
        elif action == "diff":
            diff = prov.get_diff()
            return {"status": "success", "action": "diff", "diff": diff.model_dump()}
        elif action == "status":
            st = prov.get_status()
            return {"status": "success", "action": "status", "working_copy_status": st.model_dump()}
        else:
            return {"status": "error", "message": f"Unsupported SVN action '{action}'"}
    except Exception as exc:
        return {"status": "error", "provider": "svn", "action": action, "message": str(exc)}


def vcs_audit_records(provider: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Retrieve structured audit log records of recent repository operations."""
    try:
        from nexcoder_planning.vcs import get_vcs_audit_logger

        logger = get_vcs_audit_logger()
        records = logger.list_records(provider=provider, limit=limit)
        return {
            "status": "success",
            "count": len(records),
            "records": [r.model_dump() for r in records],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
