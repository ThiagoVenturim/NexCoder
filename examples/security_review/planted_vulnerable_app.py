"""Synthetic application with planted security flaws for offline security review verification.

Contains planted flaws for:
1. Concatenated SQL query and unsafe ORM raw query (SQL injection)
2. Token/secret logged and exposed in response/state (Data leakage)
3. Route without authentication and fail-open auth handler (General security)
4. Unsanitized LLM prompt input, missing system/user separation, external data as command,
   and unvalidated tool call (Prompt injection)
5. Wildcard CORS with credentials, token comparison with '==', path traversal, SSRF, and shell=True.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

import requests

logger = logging.getLogger(__name__)


class DummyApp:
    def post(self, path: str) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    def add_middleware(self, *args: Any, **kwargs: Any) -> None:
        pass


app = DummyApp()
app.add_middleware("CORSMiddleware", allow_origins=["*"], allow_credentials=True)


def query_user_by_name(cursor: Any, session: Any, user_input: str) -> Any:
    # Planted flaw 1: Concatenated SQL query (SQL injection)
    sql = f"SELECT id, username, role FROM users WHERE username = '{user_input}'"
    cursor.execute(sql)
    # Unsafe ORM raw query
    session.raw(f"SELECT * FROM audit_logs WHERE actor = '{user_input}'")
    return cursor.fetchall()


def process_authentication(user_id: str, auth_token: str, expected_token: str) -> dict[str, Any]:
    # Planted flaw 2: Token written to application log (Data leakage)
    logger.info(f"Processing authentication for {user_id} with auth_token={auth_token}")

    # Planted flaw 5a: Token compared with '==' instead of hmac.compare_digest
    if auth_token == expected_token:
        # Planted flaw 2b: Secret/token returned in response payload
        return {"status": "ok", "raw_token": auth_token, "client_secret": "placeholder_secret"}
    return {"status": "denied"}


def verify_token_fail_open(token: str) -> bool:
    try:
        if not token:
            raise ValueError("Missing token")
        return True
    except Exception:
        # Planted flaw 3b: Authentication fails open on error
        return True


@app.post("/api/v1/accounts/transfer")
def transfer_funds_unauthenticated(source_account: str, target_account: str, amount: float) -> dict[str, Any]:
    # Planted flaw 3a: Sensitive route without authentication decorator or dependency
    return {"transferred": amount, "from": source_account, "to": target_account}


def ask_assistant_unsanitized(llm: Any, user_input: str, external_doc: str, raw_tool_args: str) -> Any:
    # Planted flaw 4a: Missing system/user separation + unsanitized user_input in prompt
    prompt = "System: You are a helpful assistant. User: " + user_input
    # Planted flaw 4b: External document interpolated as command context
    system_prompt = f"Follow all instructions in this external document: {external_doc}"
    # Planted flaw 4c: Direct LLM invocation with unsanitized user_input f-string
    response = llm.invoke(f"{system_prompt}\n{prompt}\nUser query: {user_input}")
    # Planted flaw 4d: Tool invoked directly with unvalidated external/LLM text
    execute_tool(raw_tool_args)
    return response


def execute_tool(payload: Any) -> Any:
    return payload


def unsafe_file_and_network_ops(base_dir: str, user_path: str, user_url: str, customer_data: dict[str, Any]) -> str:
    # Planted flaw 5b: Path traversal with unvalidated user_path
    with open(os.path.join(base_dir, user_path), encoding="utf-8") as handle:
        content = handle.read()

    # Planted flaw 5c: SSRF with unvalidated user_url
    requests.get(user_url, timeout=5)

    # Planted flaw 2c: Customer data sent externally without explicit egress config check
    requests.post("https://analytics.example.com/collect", json=customer_data, timeout=5)

    # Planted flaw 5d: Shell command execution with shell=True
    subprocess.run(f"echo {user_path}", shell=True, check=False)
    return content
