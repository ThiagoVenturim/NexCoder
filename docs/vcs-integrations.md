# VCS and Repository Management Integrations

NexCoder provides a unified repository and version control management abstraction layer (`nexcoder_planning.vcs`). This layer enables autonomous agents, CI/CD systems, and engineers to operate seamlessly across heterogenous platforms using a uniform provider interface.

Supported platforms and tools include:
- **Azure DevOps**: Git repositories, Azure Boards work items, Pull Requests, and Azure Pipelines.
- **GitLab**: Projects, Issues, Merge Requests, and GitLab CI/CD pipelines.
- **Subversion (SVN)**: Working copy lifecycle (checkout, add, commit, log, diff, status, update) via the `svn` CLI.
- **TortoiseGit**: Windows GUI integration on top of standard Git, offering CLI shortcuts and batch automation.
- **Git**: High-level reusable local and remote Git workflows enforcing conventional commits, zero emoji policies, and stripping AI co-author trailers.

---

## Architecture and Common Interface

All platforms inherit from `RepoManagementProvider`, ensuring consistent interaction patterns regardless of whether the target system is cloud-hosted or local CLI-driven.

```
+--------------------------------------------------------------------------+
|                        RepoManagementProvider                            |
|  - capabilities: {"repositories", "issues", "pull_requests", ...}       |
|  - secure_compare(a, b): constant-time HMAC digest comparison            |
|  - load_secret_from_env(*vars): safe environment secret resolution       |
|  - audit_logger: automated credential redaction and event recording      |
+------------------------------------+-------------------------------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+-----------------+         +-----------------+         +-----------------+
| AzureDevOps     |         | GitLabProvider  |         | GitProvider     |
| Provider        |         |                 |         |                 |
| - Repos API     |         | - Projects API  |         | - Branch / Tag  |
| - Boards (WIQL) |         | - Issues API    |         | - Commit / Log  |
| - Pull Requests |         | - Merge Requests|         | - Diff / Status |
| - Pipelines     |         | - CI Pipelines  |         | - Push / Pull   |
+-----------------+         +-----------------+         +--------+--------+
                                                                 |
                                       +-------------------------+
                                       |                         |
                                       v                         v
                              +-----------------+       +-----------------+
                              | SVNProvider     |       | TortoiseGit     |
                              |                 |       | Provider        |
                              | - Checkout      |       | - Git Engine    |
                              | - Commit / Log  |       | - TortoiseProc  |
                              | - Diff / Status |       | - Batch scripts |
                              +-----------------+       +-----------------+
```

### Provider Capabilities

Providers explicitly declare supported capabilities:
- `repositories`: Querying and provisioning repositories/projects.
- `issues`: Backlog and bug tracking (issues or work items).
- `pull_requests`: Code review workflows (pull requests or merge requests).
- `pipelines`: Continuous integration builds and pipeline triggers.
- `vcs`: Working tree version control operations (checkout, commit, diff, log).

---

## Platform Details

### 1. Azure DevOps (`AzureDevOpsProvider`)

Integrates with Azure DevOps Services and Server REST API v7.0.

- **Authentication**: Personal Access Token (PAT) or OAuth bearer token. Loaded from `AZURE_DEVOPS_PAT` or `AZURE_DEVOPS_TOKEN` environment variables.
- **Repositories**: Fetches repositories and metadata via `/_apis/git/repositories`.
- **Work Items / Boards**: Queries items using WIQL (Work Item Query Language) and creates or updates tasks with JSON Patch operations (`application/json-patch+json`).
- **Pull Requests**: Manages PR lifecycle, reviewer status, and completion/merging with merge commit message customization.
- **Pipelines**: Lists pipelines, inspects runs, and triggers builds with custom runtime parameters and branch targets.

### 2. GitLab (`GitLabProvider`)

Integrates with GitLab REST API v4.

- **Authentication**: Personal Access Token or CI Job Token (`PRIVATE-TOKEN` header). Loaded from `GITLAB_TOKEN` or `GITLAB_API_TOKEN`.
- **Projects**: Project metadata retrieval and provisioning.
- **Issues**: Issue tracking with labels, description markdown, and state events (`close`, `reopen`).
- **Merge Requests**: Branch-to-branch code review, draft/WIP markers, and automatic merge execution.
- **CI/CD**: Pipeline trigger endpoint (`/api/v4/projects/{id}/pipeline`) and pipeline execution monitoring.

### 3. Subversion (`SVNProvider`)

Integrates with Subversion repositories using the standard `svn` CLI executable.

- **Checkout**: `svn checkout -r {revision} {url} {destination}`
- **Commit**: `svn commit -m "{message}" {files}` (validates conventional commit structure, zero emojis, and attribution stripping).
- **Log**: Structured XML output parsing (`svn log -l {limit} --xml`).
- **Diff**: Unified diff generation (`svn diff`).
- **Status**: Working copy changes classification (modified `M`, added `A`, deleted `D`, untracked `?`).
- **Update**: Synchronizing working copy with remote trunk or branches.

### 4. TortoiseGit (`TortoiseGitProvider`)

Designed for Windows environments where engineers leverage the TortoiseGit shell extension.

- **Engine**: Inherits from `GitProvider`, executing standard Git commands headless when run in scripts or pipelines.
- **GUI Command Launcher**: Constructs command lines for `TortoiseGitProc.exe`, launching GUI dialogs:
  - `/command:commit /path:"..." /logmsg:"..."`
  - `/command:log /path:"..."`
  - `/command:diff /path:"..."`
  - `/command:push /path:"..."`
  - `/command:pull /path:"..."`
  - `/command:repostatus /path:"..."`
- **Batch Shortcuts**: Generates convenient Windows batch launchers (`.bat`) inside repositories for rapid terminal-to-GUI dispatch.
- **Detection**: Automatically locates `TortoiseGitProc.exe` in standard 64-bit and 32-bit `Program Files` paths or on system `PATH`.

### 5. Git (`GitProvider`)

Provides headless, reproducible Git operations with strict quality enforcement:

- **Emoji Rejection**: Scans all branch names and commit messages, rejecting Unicode pictographs and emojis.
- **Attribution Sanitization**: Automatically strips AI co-author trailers (`Co-Authored-By`, `Generated with`, `Generated-by`).
- **Conventional Commits**: Enforces standardized types (`feat`, `fix`, `docs`, `chore`, `test`, `ci`, `refactor`, `perf`).

---

## Security, Secret Handling, and Audit Logging

### 1. Token Isolation in Environment Variables

Tokens and credentials are never stored in source code, committed files, or configuration trees. Providers load tokens using `load_secret_from_env()`, inspecting predefined variables (`AZURE_DEVOPS_PAT`, `GITLAB_TOKEN`, `SVN_PASSWORD`).

### 2. Timing-Attack Safe Comparison

Token comparisons use Python's `hmac.compare_digest` in `RepoManagementProvider.secure_compare()`, preventing side-channel timing analysis attacks.

### 3. Structured Audit Trail with Credential Redaction

Every operation performed through any provider is audited through `VCSAuditLogger`. Audit logs record:
- `timestamp`: UTC ISO-8601 timestamp.
- `provider`: Platform identifier (`azure_devops`, `gitlab`, `git`, `svn`, `tortoise_git`).
- `action`: Operation name (`create_issue`, `merge_pull_request`, `checkout`, `commit`).
- `resource_type` and `resource_id`: Target entity identifier.
- `success`: Boolean status.
- `details`: Metadata dictionary with automatic redaction of sensitive keys (`token`, `pat`, `password`, `authorization`, `secret`).

---

## Offline Testing and Determinism

All provider tests execute 100% offline without accessing external servers or depending on pre-installed external services:
- **Azure DevOps & GitLab**: Tested using `httpx.MockTransport`, intercepting requests and returning realistic REST payloads.
- **Subversion**: Tested using an in-process local test repository runner (`LocalSVNTestRepo`) that simulates SVN command behaviors, XML logs, and unified diffs.
- **Git & TortoiseGit**: Tested using simulated command execution runners and local temporary directories.

---

## CLI Usage

The NexCoder CLI exposes VCS and repository management commands under `nexcoder vcs`:

```bash
# List repositories
nexcoder vcs repos --provider gitlab --org 999
nexcoder vcs repos --provider azure_devops --org myorg --project myproj

# Manage issues
nexcoder vcs issues --provider gitlab --org 999 --action list
nexcoder vcs issues --provider azure_devops --org myorg --project myproj --action create --title "Payment Gateway" --body "Implement Stripe"

# Manage pull requests
nexcoder vcs prs --provider gitlab --org 999 --action list
nexcoder vcs prs --provider azure_devops --org myorg --project myproj --action create --title "feat: payment" --source feature/pay --target develop

# Subversion operations
nexcoder vcs svn --action status --dest .
nexcoder vcs svn --action log --dest . --rev HEAD

# TortoiseGit shortcuts
nexcoder vcs tortoise --command commit --path .

# Inspect audit logs
nexcoder vcs audit --limit 20
```
