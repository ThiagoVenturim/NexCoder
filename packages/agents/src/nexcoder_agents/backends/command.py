"""Agent backends that speak the NexCoder wire protocol over a subprocess.

``CommandAgentBackend`` runs any argv that implements the protocol (a stub in tests,
a local entrypoint during development). ``ContainerCLIBackend`` builds a ``docker``
(or ``podman``) command line around the agent CLI image in ``docker/agent-cli``.

Both route the prompt through ``PromptFirewall`` first and, when given a control
plane audit log and cost tracker, record every dispatch there. Prompt text is never
written to the audit log; only its length and SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from nexcoder_control.approval.target_gate import redact_secrets
from nexcoder_control.metering.audit import AppendOnlyAuditLog, AuditSeverity
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_core.llm.firewall import PromptFirewall, redact_secrets_text
from pydantic import BaseModel, Field, field_validator

from nexcoder_agents.backends.base import AgentBackend, AgentResult, AgentTask
from nexcoder_agents.backends.protocol import ProtocolError, encode_request, parse_result

Runner = Callable[..., subprocess.CompletedProcess[str]]

DEFAULT_TIMEOUT_S = 300.0
HOST_GRACE_S = 15.0
_STDERR_TAIL = 2000
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SECRET_ENV_FRAGMENTS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "COOKIE", "SESSION")


_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*(?:token|password|passwd|secret|api[_-]?key|authorization|cookie|session)[A-Za-z0-9_-]*)"
    r"(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)


def redact_text(text: str) -> str:
    """Mask known secret formats and `name=value` pairs whose name looks like a credential."""
    return _KEY_VALUE_SECRET.sub(r"\1\2[REDACTED_SECRET]", redact_secrets_text(text))


def _tail(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return redact_text(text.strip()[-_STDERR_TAIL:])


class CommandAgentBackend(AgentBackend):
    """Run an argv that implements the NexCoder agent protocol on stdin/stdout."""

    name = "command"

    def __init__(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        runner: Runner | None = None,
        env: dict[str, str] | None = None,
        firewall: PromptFirewall | None = None,
        use_firewall: bool = True,
        audit_log: AppendOnlyAuditLog | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        if not argv:
            raise ValueError("argv must not be empty")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._argv = [str(a) for a in argv]
        self.timeout_s = timeout_s
        self._runner: Runner = runner or subprocess.run
        self._env = env
        self._firewall = (firewall or PromptFirewall.get_default()) if use_firewall else None
        self.audit_log = audit_log
        self.cost_tracker = cost_tracker

    # -- hooks for subclasses -------------------------------------------------

    def build_command(self, task: AgentTask) -> list[str]:
        """Return the argv used to run ``task``."""
        return list(self._argv)

    def on_host_timeout(self, task: AgentTask) -> None:
        """Called after the host-side timeout fired. Subclasses clean up here."""

    # -- main flow --------------------------------------------------------------

    def run(self, task: AgentTask) -> AgentResult:
        timeout = task.timeout_s or self.timeout_s

        if self._firewall is not None:
            inspection = self._firewall.inspect_prompt(task.prompt, actor=task.actor, raise_on_block=False)
            if inspection.blocked:
                reasons = ", ".join(v.rule_id for v in inspection.violations) or "blocked by prompt firewall"
                result = AgentResult(task_id=task.task_id, backend=self.name, status="blocked", error=reasons)
                self._audit(task, "agent.backend.blocked", result)
                return result

        self._audit(task, "agent.backend.dispatched", None, extra={"timeout_s": timeout})
        started = time.monotonic()
        result = self._execute(task, timeout)
        result.duration_s = round(time.monotonic() - started, 3)
        self._audit(task, "agent.backend.completed", result)
        self._meter(task, result)
        return result

    def _execute(self, task: AgentTask, timeout: float) -> AgentResult:
        argv = self.build_command(task)
        request = encode_request(task, timeout)
        try:
            proc = self._runner(
                argv,
                input=request,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + HOST_GRACE_S,
                check=False,
                env=self._env,
            )
        except subprocess.TimeoutExpired as exc:
            self.on_host_timeout(task)
            return self._failure(task, "timeout", f"no result after {timeout + HOST_GRACE_S:.0f}s", exc.stderr)
        except FileNotFoundError:
            return self._failure(task, "error", f"executable not found: {argv[0]}")
        except OSError as exc:
            return self._failure(task, "error", f"could not start {argv[0]}: {exc.strerror or exc}")

        try:
            result = parse_result(proc.stdout or "", task_id=task.task_id, backend=self.name)
        except ProtocolError as exc:
            detail = f"exit code {proc.returncode}: {exc}"
            return self._failure(task, "error", detail, proc.stderr)
        if isinstance(result.data.get("stderr_tail"), str):
            result.data["stderr_tail"] = _tail(result.data["stderr_tail"])
        if result.error:
            result.error = redact_text(result.error)
        return result

    def _failure(
        self,
        task: AgentTask,
        status: Literal["error", "timeout"],
        message: str,
        stderr: str | bytes | None = None,
    ) -> AgentResult:
        tail = _tail(stderr)
        return AgentResult(
            task_id=task.task_id,
            backend=self.name,
            status=status,
            error=message,
            data={"stderr_tail": tail} if tail else {},
        )

    # -- control plane ------------------------------------------------------

    def _audit(
        self,
        task: AgentTask,
        event_type: str,
        result: AgentResult | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.audit_log is None:
            return
        details: dict[str, Any] = {
            "backend": self.name,
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "pipeline_id": task.pipeline_id,
            "prompt_chars": len(task.prompt),
            "prompt_sha256": hashlib.sha256(task.prompt.encode("utf-8")).hexdigest(),
        }
        severity: AuditSeverity = "info"
        if result is not None:
            details.update(
                {
                    "status": result.status,
                    "model": result.model,
                    "duration_s": result.duration_s,
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "reported_cost_usd": result.reported_cost_usd,
                    "error": result.error,
                }
            )
            if not result.ok:
                severity = "warning"
        if extra:
            details.update(extra)
        self.audit_log.record_event(
            event_type=event_type,
            actor=task.actor,
            action="dispatch",
            resource=f"{self.name}:{task.task_id}",
            severity=severity,
            details=redact_secrets(details),
        )

    def _meter(self, task: AgentTask, result: AgentResult) -> None:
        if self.cost_tracker is None or result.status == "blocked":
            return
        self.cost_tracker.record_usage(
            model=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            app_id=task.app_id,
            person_id=task.actor,
            agent_id=task.agent_id,
            pipeline_id=task.pipeline_id,
            metadata={
                "backend": self.name,
                "task_id": task.task_id,
                "status": result.status,
                "reported_cost_usd": result.reported_cost_usd,
            },
        )


class ContainerBackendConfig(BaseModel):
    """How to reach the agent CLI container. Credentials live in a named volume, never in the image."""

    runtime: str = "docker"
    image: str = "nexcoder/agent-cli:local"
    mode: Literal["run", "exec"] = "run"
    container_name: str = "nexcoder-agent-cli"
    cli: str = "claude"
    credentials_volume: str = "nexcoder-agent-cli-home"
    credentials_mount: str = "/home/agent"
    workspace_dir: Path | None = None
    workspace_read_only: bool = True
    network: str | None = None
    memory: str = "2g"
    cpus: str = "2"
    pids_limit: int = Field(default=256, gt=0)
    read_only_rootfs: bool = True
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0)
    extra_env: dict[str, str] = Field(default_factory=dict)

    @field_validator("credentials_volume", "container_name", "cli")
    @classmethod
    def _safe_name(cls, value: str) -> str:
        if not _SAFE_NAME.match(value):
            raise ValueError(f"{value!r} must be a plain name (letters, digits, '_', '.', '-'), not a path")
        return value

    @field_validator("runtime", "image", "memory", "cpus")
    @classmethod
    def _not_an_option(cls, value: str) -> str:
        if not value or value.startswith("-") or any(ch.isspace() for ch in value):
            raise ValueError(f"{value!r} must be a single non-empty token that does not start with '-'")
        return value

    @field_validator("credentials_mount")
    @classmethod
    def _absolute_mount(cls, value: str) -> str:
        if not value.startswith("/") or ":" in value:
            raise ValueError("credentials_mount must be an absolute path inside the container")
        return value

    @field_validator("extra_env")
    @classmethod
    def _no_secrets_on_command_line(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                raise ValueError(f"invalid environment variable name: {key!r}")
            if any(frag in key.upper() for frag in _SECRET_ENV_FRAGMENTS):
                raise ValueError(
                    f"{key} looks like a credential; log in inside the container instead of passing secrets as env"
                )
        return value


class ContainerCLIBackend(CommandAgentBackend):
    """Dispatch tasks to the agent CLI image (``docker/agent-cli``) through docker or podman."""

    name = "container"

    def __init__(self, config: ContainerBackendConfig | None = None, **kwargs: Any) -> None:
        self.config = config or ContainerBackendConfig()
        kwargs.setdefault("timeout_s", self.config.timeout_s)
        super().__init__([self.config.runtime], **kwargs)

    @staticmethod
    def container_name_for(task: AgentTask) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "-", task.task_id)[:48].strip("-.") or "task"
        return f"nexcoder-agent-{safe}"

    def build_command(self, task: AgentTask) -> list[str]:
        cfg = self.config
        env_args: list[str] = ["-e", f"NEXCODER_AGENT_CLI={cfg.cli}"]
        for key, value in sorted(cfg.extra_env.items()):
            env_args += ["-e", f"{key}={value}"]

        if cfg.mode == "exec":
            return [cfg.runtime, "exec", "-i", *env_args, cfg.container_name, "nexcoder-agent", "run"]

        argv = [
            cfg.runtime,
            "run",
            "--rm",
            "-i",
            "--name",
            self.container_name_for(task),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(cfg.pids_limit),
            "--memory",
            cfg.memory,
            "--cpus",
            cfg.cpus,
            *env_args,
        ]
        if cfg.read_only_rootfs:
            argv += ["--read-only", "--tmpfs", "/tmp:rw,size=256m"]  # noqa: S108 - tmpfs inside the container
        argv += [
            "-v",
            f"{cfg.credentials_volume}:{cfg.credentials_mount}",
        ]
        if cfg.workspace_dir is not None:
            suffix = ":ro" if cfg.workspace_read_only else ""
            argv += ["-v", f"{Path(cfg.workspace_dir).resolve()}:/workspace{suffix}", "-w", "/workspace"]
        if cfg.network:
            argv += ["--network", cfg.network]
        argv += [cfg.image, "run"]
        return argv

    def on_host_timeout(self, task: AgentTask) -> None:
        if self.config.mode != "run":
            return
        try:
            self._runner(
                [self.config.runtime, "rm", "-f", self.container_name_for(task)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
