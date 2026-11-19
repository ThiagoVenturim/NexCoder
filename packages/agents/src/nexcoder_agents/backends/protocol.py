"""Wire protocol between NexCoder and an agent CLI entrypoint.

NexCoder writes one JSON request to the entrypoint's stdin and reads one JSON
result from its stdout. Anything else the CLI prints (progress, warnings) may come
before the result; the result is the last line that parses as a JSON object with
the expected ``protocol`` field.

Request::

    {"protocol": "nexcoder.agent-task/v1", "task_id": "...", "prompt": "...",
     "system_prompt": null, "timeout_s": 300}

Result::

    {"protocol": "nexcoder.agent-result/v1", "task_id": "...", "status": "ok",
     "output": "...", "model": "...", "usage": {"input_tokens": 0, "output_tokens": 0},
     "cost_usd": 0.0, "error": null, "data": {}}

The container entrypoint in ``docker/agent-cli/entrypoint.py`` implements the other
side with the standard library only and keeps the same constants.
"""

from __future__ import annotations

import json
from typing import Any

from nexcoder_agents.backends.base import AgentResult, AgentTask, AgentUsage

REQUEST_PROTOCOL = "nexcoder.agent-task/v1"
RESULT_PROTOCOL = "nexcoder.agent-result/v1"
MAX_OUTPUT_CHARS = 200_000


class ProtocolError(ValueError):
    """The entrypoint answered with something that is not a valid result."""


def encode_request(task: AgentTask, timeout_s: float) -> str:
    """Serialize a task into the request line sent on stdin."""
    payload = {
        "protocol": REQUEST_PROTOCOL,
        "task_id": task.task_id,
        "prompt": task.prompt,
        "system_prompt": task.system_prompt,
        "timeout_s": timeout_s,
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _find_result_object(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("protocol") == RESULT_PROTOCOL:
            return obj
    raise ProtocolError("no result object found on stdout")


def _as_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def parse_result(stdout: str, *, task_id: str, backend: str, duration_s: float = 0.0) -> AgentResult:
    """Parse the entrypoint's stdout into an ``AgentResult``.

    Raises ``ProtocolError`` when no valid result is present or when it belongs to
    another task.
    """
    obj = _find_result_object(stdout)
    if obj.get("task_id") not in (None, task_id):
        raise ProtocolError(f"result task_id {obj.get('task_id')!r} does not match {task_id!r}")
    status = obj.get("status")
    if status not in ("ok", "error", "timeout"):
        raise ProtocolError(f"invalid status {status!r}")
    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
    cost = obj.get("cost_usd")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    error = obj.get("error")
    return AgentResult(
        task_id=task_id,
        backend=backend,
        status=status,
        output=str(obj.get("output") or "")[:MAX_OUTPUT_CHARS],
        model=str(obj.get("model") or "unknown"),
        usage=AgentUsage(
            input_tokens=_as_int(usage.get("input_tokens")),
            output_tokens=_as_int(usage.get("output_tokens")),
        ),
        reported_cost_usd=float(cost) if isinstance(cost, int | float) else None,
        duration_s=duration_s,
        error=str(error) if error else None,
        data=data,
    )
