"""Extract JSON from model output.

Models wrap JSON in prose, code fences, or both. ``extract_json`` returns the
first JSON object or array it can parse, or ``None``.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _scan_balanced(text: str, start: int) -> str | None:
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Any | None:
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for i, ch in enumerate(candidate):
            if ch in "{[":
                chunk = _scan_balanced(candidate, i)
                if chunk:
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
    return None
