#!/usr/bin/env python3
"""Headless entrypoint for the NexCoder agent CLI container.

Standard library only, so the image does not need the NexCoder packages.

Subcommands:
  run     read one JSON task from stdin, run the agent CLI in print mode, write one
          JSON result line to stdout (protocol nexcoder.agent-result/v1)
  check   report whether the agent CLI is installed (no task, no network)
  login   start the agent CLI interactively so the user can log in; the login is
          stored in the mounted home volume, never in the image
  idle    keep the container alive for ``docker exec`` mode

Environment:
  NEXCODER_AGENT_CLI       adapter: "claude" (default) or "generic"
  NEXCODER_AGENT_CLI_BIN   executable for the claude adapter (default "claude");
                           a JSON array is accepted, e.g. ["python3", "/fake.py"]
  NEXCODER_AGENT_CLI_ARGS  extra arguments appended to the claude command
  NEXCODER_AGENT_CLI_CMD   full command for the generic adapter (JSON array or a
                           shell-like string); it receives the prompt on stdin and
                           its stdout is the output
  NEXCODER_AGENT_MODEL     optional model name passed to the claude adapter

The wire protocol is mirrored from nexcoder_agents/backends/protocol.py.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Any

REQUEST_PROTOCOL = "nexcoder.agent-task/v1"
RESULT_PROTOCOL = "nexcoder.agent-result/v1"
DEFAULT_TIMEOUT_S = 300.0
MAX_PROMPT_CHARS = 400_000
MAX_OUTPUT_CHARS = 200_000
STDERR_TAIL = 2000


class EntrypointError(Exception):
    """A problem with the request or the configuration (reported as status "error")."""


def parse_argv(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EntrypointError(f"invalid JSON argv: {exc.msg}") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise EntrypointError("a JSON argv must be a list of strings")
        return parsed
    return shlex.split(value)


def emit(task_id: str | None, status: str, **fields: Any) -> None:
    payload: dict[str, Any] = {
        "protocol": RESULT_PROTOCOL,
        "task_id": task_id,
        "status": status,
        "output": "",
        "model": "unknown",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_usd": None,
        "error": None,
        "data": {},
    }
    payload.update(fields)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read_request(raw: str) -> dict[str, Any]:
    line = raw.strip()
    if not line:
        raise EntrypointError("empty request on stdin")
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        raise EntrypointError(f"request is not valid JSON: {exc.msg}") from exc
    if not isinstance(request, dict):
        raise EntrypointError("request must be a JSON object")
    if request.get("protocol") != REQUEST_PROTOCOL:
        raise EntrypointError(f"unsupported protocol {request.get('protocol')!r}")
    prompt = request.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise EntrypointError("prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise EntrypointError(f"prompt longer than {MAX_PROMPT_CHARS} characters")
    system_prompt = request.get("system_prompt")
    if system_prompt is not None and not isinstance(system_prompt, str):
        raise EntrypointError("system_prompt must be a string or null")
    timeout = request.get("timeout_s", DEFAULT_TIMEOUT_S)
    if not isinstance(timeout, int | float) or timeout <= 0:
        raise EntrypointError("timeout_s must be a positive number")
    return request


def build_command(adapter: str, request: dict[str, Any]) -> list[str]:
    if adapter == "claude":
        argv = parse_argv(os.environ.get("NEXCODER_AGENT_CLI_BIN", "claude")) or ["claude"]
        argv += ["-p", "--output-format", "json"]
        model = os.environ.get("NEXCODER_AGENT_MODEL", "").strip()
        if model:
            argv += ["--model", model]
        if request.get("system_prompt"):
            argv += ["--append-system-prompt", request["system_prompt"]]
        argv += parse_argv(os.environ.get("NEXCODER_AGENT_CLI_ARGS", ""))
        return argv
    if adapter == "generic":
        argv = parse_argv(os.environ.get("NEXCODER_AGENT_CLI_CMD", ""))
        if not argv:
            raise EntrypointError("the generic adapter needs NEXCODER_AGENT_CLI_CMD")
        return argv
    raise EntrypointError(f"unknown adapter {adapter!r} (use claude or generic)")


def _int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def parse_claude_output(stdout: str) -> dict[str, Any]:
    """Map the JSON printed by ``claude -p --output-format json`` to result fields."""
    data: dict[str, Any] | None = None
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            data = candidate
            break
    if data is None:
        try:
            whole = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise EntrypointError("agent CLI did not print a JSON result") from exc
        if isinstance(whole, list):
            results = [item for item in whole if isinstance(item, dict) and item.get("type") == "result"]
            whole = results[-1] if results else None
        if not isinstance(whole, dict):
            raise EntrypointError("agent CLI did not print a JSON result")
        data = whole

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    model_usage = data.get("modelUsage") if isinstance(data.get("modelUsage"), dict) else {}
    model = data.get("model") or (next(iter(model_usage)) if model_usage else "unknown")
    cost = data.get("total_cost_usd", data.get("cost_usd"))
    is_error = bool(data.get("is_error")) or data.get("subtype") not in (None, "success")
    output = str(data.get("result") or "")
    return {
        "status": "error" if is_error else "ok",
        "output": output[:MAX_OUTPUT_CHARS],
        "model": str(model),
        "usage": {
            "input_tokens": _int(usage.get("input_tokens")),
            "output_tokens": _int(usage.get("output_tokens")),
        },
        "cost_usd": float(cost) if isinstance(cost, int | float) else None,
        "error": (output or str(data.get("subtype") or "agent CLI reported an error")) if is_error else None,
        "data": {
            "session_id": data.get("session_id"),
            "num_turns": data.get("num_turns"),
        },
    }


_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*(?:token|password|passwd|secret|api[_-]?key|authorization|cookie|session)[A-Za-z0-9_-]*)"
    r"(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)


def _tail(text: str | bytes | None) -> str:
    """Last part of stderr with `name=value` credentials masked (the host redacts again)."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return _KEY_VALUE_SECRET.sub(r"\1\2[REDACTED_SECRET]", text.strip()[-STDERR_TAIL:])


def cmd_run() -> int:
    task_id: str | None = None
    try:
        request = read_request(sys.stdin.readline())
        task_id = request.get("task_id") if isinstance(request.get("task_id"), str) else None
        adapter = os.environ.get("NEXCODER_AGENT_CLI", "claude").strip().lower()
        argv = build_command(adapter, request)
    except EntrypointError as exc:
        emit(task_id, "error", error=str(exc))
        return 0

    timeout = float(request.get("timeout_s", DEFAULT_TIMEOUT_S))
    stdin_text = request["prompt"]
    if adapter != "claude" and request.get("system_prompt"):
        stdin_text = f"{request['system_prompt']}\n\n{stdin_text}"
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - argv list from the container's own configuration
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        emit(
            task_id,
            "timeout",
            error=f"agent CLI did not finish within {timeout:.0f}s",
            data={"stderr_tail": _tail(exc.stderr)},
        )
        return 0
    except FileNotFoundError:
        emit(task_id, "error", error=f"agent CLI not found: {argv[0]}")
        return 0
    except OSError as exc:
        emit(task_id, "error", error=f"could not start the agent CLI: {exc.strerror or exc}")
        return 0

    duration = round(time.monotonic() - started, 3)
    stderr_tail = _tail(proc.stderr)
    if adapter == "claude":
        try:
            fields = parse_claude_output(proc.stdout or "")
        except EntrypointError as exc:
            emit(task_id, "error", error=f"exit code {proc.returncode}: {exc}", data={"stderr_tail": stderr_tail})
            return 0
        if proc.returncode != 0 and fields["status"] == "ok":
            fields["status"] = "error"
            fields["error"] = f"agent CLI exited with code {proc.returncode}"
    else:
        ok = proc.returncode == 0
        fields = {
            "status": "ok" if ok else "error",
            "output": (proc.stdout or "").strip()[:MAX_OUTPUT_CHARS],
            "model": os.environ.get("NEXCODER_AGENT_MODEL", "").strip() or adapter,
            "error": None if ok else f"agent CLI exited with code {proc.returncode}",
            "data": {},
        }
    fields["data"] = {**fields.get("data", {}), "duration_s": duration, "exit_code": proc.returncode}
    if stderr_tail and fields["status"] != "ok":
        fields["data"]["stderr_tail"] = stderr_tail
    emit(task_id, fields.pop("status"), **fields)
    return 0


def cmd_check() -> int:
    adapter = os.environ.get("NEXCODER_AGENT_CLI", "claude").strip().lower()
    try:
        if adapter == "claude":
            argv = (parse_argv(os.environ.get("NEXCODER_AGENT_CLI_BIN", "claude")) or ["claude"]) + ["--version"]
        else:
            argv = build_command(adapter, {})
            argv = [argv[0], "--version"]
    except EntrypointError as exc:
        print(json.dumps({"ok": False, "adapter": adapter, "error": str(exc)}))
        return 1
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "adapter": adapter, "error": f"cannot run {argv[0]}: {exc}"}))
        return 1
    version = (proc.stdout or proc.stderr or "").strip().splitlines()[:1]
    print(json.dumps({"ok": proc.returncode == 0, "adapter": adapter, "version": version[0] if version else ""}))
    return 0 if proc.returncode == 0 else 1


def cmd_login() -> int:
    adapter = os.environ.get("NEXCODER_AGENT_CLI", "claude").strip().lower()
    if adapter == "claude":
        argv = parse_argv(os.environ.get("NEXCODER_AGENT_CLI_BIN", "claude")) or ["claude"]
    else:
        argv = build_command(adapter, {})[:1]
    print("Starting the agent CLI interactively. Log in with your own account; the login is kept in the")
    print("mounted home volume. Exit the CLI when done.", flush=True)
    os.execvp(argv[0], argv)  # noqa: S606 - replaces this process with the CLI for an interactive login
    return 1


def cmd_idle() -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(3600)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "check"
    handlers = {"run": cmd_run, "check": cmd_check, "login": cmd_login, "idle": cmd_idle}
    handler = handlers.get(command)
    if handler is None:
        print(f"usage: nexcoder-agent {{{','.join(handlers)}}}", file=sys.stderr)
        return 2
    return handler()


if __name__ == "__main__":
    sys.exit(main())
