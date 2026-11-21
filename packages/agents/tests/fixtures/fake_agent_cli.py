"""Fake agent CLI used by the backend tests. No network, no real model.

Mimics ``claude -p --output-format json``: reads the prompt on stdin and prints one
JSON object. Keywords in the prompt choose the behaviour:

  SLEEP    sleep 30 seconds (timeout tests)
  CRASH    print to stderr and exit with code 3
  ISERROR  print a result with is_error true
  GARBAGE  print text that is not JSON
  --version (argument) print a version line
"""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    if "--version" in sys.argv[1:]:
        print("0.0.0-fake (Fake Agent CLI)")
        return 0
    prompt = sys.stdin.read()
    if "SLEEP" in prompt:
        time.sleep(30)
    if "CRASH" in prompt:
        print("fake failure: token=abc123secretvalue", file=sys.stderr)
        return 3
    if "GARBAGE" in prompt:
        print("this is not json")
        return 0
    words = len(prompt.split())
    is_error = "ISERROR" in prompt
    system = ""
    if "--append-system-prompt" in sys.argv:
        system = sys.argv[sys.argv.index("--append-system-prompt") + 1]
    print("progress: thinking", flush=True)
    print(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": is_error,
                "result": "fake failure" if is_error else f"done: {words} words; system={system or '-'}",
                "session_id": "fake-session",
                "num_turns": 1,
                "total_cost_usd": 0.0012,
                "usage": {"input_tokens": words, "output_tokens": 7},
                "modelUsage": {"fake-model-1": {"inputTokens": words, "outputTokens": 7}},
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
