# Agent CLI container backend

This folder builds a container image with an agent CLI (Claude Code by default)
and a headless entrypoint. NexCoder sends a task to it through
`ContainerCLIBackend` and reads back a structured JSON result. People who do not
have a paid API key can use the subscription or login they already have for that
CLI.

NexCoder still defaults to the offline backend. The container backend only runs
when you select it.

## Terms of use and intended use

Read this before you use the backend.

- **Follow the terms of use of the CLI provider.** You are responsible for using
  the CLI as its provider allows. That includes rules on automation, rate limits
  and account sharing. If the terms do not allow a use, do not use this backend
  for it.
- **Use it only for yourself.** The backend is for one person running tasks with
  their own login on their own machine or infrastructure.
- **Do not resell or share access.** Do not expose the container as a service for
  other people. Do not pool one login across several users. Do not use it to sell
  access to the provider's models.
- **Do not get around limits.** Do not use the backend to avoid quotas, rate
  limits, usage policies or safety controls. You can lower the timeouts and
  resource caps, but do not raise them past what the provider allows.
- Every dispatch is recorded in the NexCoder control plane audit log
  (`AppendOnlyAuditLog`), and token usage goes to `CostTracker`. The audit log
  stores the length and SHA-256 digest of the prompt, never the prompt text.

## How credentials are handled

- The image contains no credential. The Dockerfile copies only `entrypoint.py`,
  and `.dockerignore` excludes everything else.
- You log in once, interactively, inside the container. The CLI saves the login
  in `/home/agent`, which is the named volume `nexcoder-agent-cli-home`. The
  volume stays on your machine and never goes into the repository or an image
  layer.
- `ContainerBackendConfig` rejects environment variables whose names look like
  credentials (`*TOKEN*`, `*KEY*`, `*SECRET*`, `*PASSWORD*` and similar). This
  keeps them out of `docker run` command lines and process listings.
- Error output (stderr) is cut to its last 2000 characters, and `name=value`
  pairs that look like secrets are masked before NexCoder stores them.
- To remove the login, run `docker volume rm nexcoder-agent-cli-home`.

## Container hardening

`ContainerCLIBackend` in `run` mode starts one container per task with
`--rm --cap-drop ALL --security-opt no-new-privileges --read-only`, a tmpfs at
`/tmp`, `--pids-limit 256`, `--memory 2g` and `--cpus 2`. The process runs as the
unprivileged user `agent`. The workspace (optional) is mounted read-only unless
you set `workspace_read_only=False`. You can set `network` to restrict
networking, but the CLI needs to reach its provider to work.

## Quick start

PowerShell:

```powershell
scripts/agent-cli.ps1 build
scripts/agent-cli.ps1 login        # log in with your own account, then exit the CLI
scripts/agent-cli.ps1 check
scripts/agent-cli.ps1 dispatch "Say hello in one short sentence."
```

bash:

```bash
scripts/agent-cli.sh build
scripts/agent-cli.sh login
scripts/agent-cli.sh check
scripts/agent-cli.sh dispatch "Say hello in one short sentence."
```

`dispatch` runs `python -m nexcoder_agents.cli dispatch --backend container ...`
and prints the `AgentResult` as JSON. Extra options such as `--workspace .` or
`--timeout 120` are passed through. The command exits with code 0 when the
status is `ok`.

For `podman`, set `NEXCODER_CONTAINER_RUNTIME=podman`.

### Long-running container (exec mode)

`compose.yml` starts one container that stays up (`idle`). NexCoder then uses
`docker exec` for each task, which avoids the start-up cost of a new container:

```bash
scripts/agent-cli.sh up
docker compose -f docker/agent-cli/compose.yml run --rm agent-cli login
python -m nexcoder_agents.cli dispatch "hello" --backend container --mode exec
```

Set `NEXCODER_AGENT_WORKSPACE` to the directory to mount at `/workspace`
(read-only). It defaults to the empty `docker/agent-cli/workspace` folder.

## From Python

```python
from nexcoder_agents.backends import ContainerBackendConfig, ContainerCLIBackend
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.cost_tracker import CostTracker

backend = ContainerCLIBackend(
    ContainerBackendConfig(workspace_dir=".", timeout_s=120),
    audit_log=AppendOnlyAuditLog(),
    cost_tracker=CostTracker(),
)
result = backend.dispatch("List the top-level folders of this project.", actor="me")
print(result.status, result.output, result.usage)
```

`build_agent_backend()` picks a backend by name or from `NEXCODER_AGENT_BACKEND`
(`offline`, `container`, `command`) and falls back to `offline`.

## Wire protocol

NexCoder writes one JSON line to the entrypoint's stdin:

```json
{"protocol": "nexcoder.agent-task/v1", "task_id": "task_1", "prompt": "...", "system_prompt": null, "timeout_s": 300}
```

The entrypoint prints one JSON line as its result. It may print progress lines
before it:

```json
{"protocol": "nexcoder.agent-result/v1", "task_id": "task_1", "status": "ok", "output": "...",
 "model": "...", "usage": {"input_tokens": 0, "output_tokens": 0}, "cost_usd": 0.0, "error": null, "data": {}}
```

`status` is one of `ok`, `error` or `timeout`. The backend adds `blocked` when
`PromptFirewall` rejects a prompt before dispatch. In that case nothing reaches
the container. Failures come back as result values and are never raised. A
host-side timeout (task timeout plus 15 seconds) removes the container.

## Adapters inside the image

| `NEXCODER_AGENT_CLI` | Command | Notes |
|---|---|---|
| `claude` (default) | `claude -p --output-format json` | prompt on stdin; `NEXCODER_AGENT_MODEL` adds `--model`; `NEXCODER_AGENT_CLI_ARGS` appends arguments |
| `generic` | `NEXCODER_AGENT_CLI_CMD` | any CLI that reads the prompt on stdin and prints the answer on stdout |

To use another agent CLI, install it in a derived image (`FROM nexcoder/agent-cli:local`)
and select the `generic` adapter with its own headless command. Check that CLI's
documentation for its non-interactive flags, and follow its terms of use as
described above.

## Tests

`packages/agents/tests/test_agent_backends.py` runs the real entrypoint on the host
against a fake CLI (`tests/fixtures/fake_agent_cli.py`). The tests need no Docker,
no network and no login. They cover dispatch, result parsing, timeouts, errors,
redaction, the firewall, the audit log and cost records, and the hardened
`docker run` command line.
