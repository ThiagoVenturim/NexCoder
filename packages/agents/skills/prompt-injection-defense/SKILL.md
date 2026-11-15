---
name: prompt-injection-defense
description: Detect and prevent direct and indirect LLM prompt injection, enforce system/user role separation, validate tool arguments, and configure runtime prompt monitoring.
user-invocable: true
---

# Prompt Injection Defense

Structured guidance for auditing and hardening LLM-powered applications against direct and indirect prompt injection.

## Core Vulnerability Patterns

1. **Unsanitized or Unbounded User Input**
   - **Risk**: User-controlled text interpolated directly into prompts without length limits or sanitization allows adversarial instruction overrides.
   - **Remediation**: Enforce strict character/token bounds, sanitize control tokens, and validate inputs through `RuntimeSecurityMonitor.inspect_prompt()`.

2. **External Data Treated as Executable Instructions (Indirect Injection)**
   - **Risk**: Documents, web pages, RAG chunks, emails, or webhook payloads concatenated into system instructions allow third-party content to hijack agent behavior.
   - **Remediation**: Isolate external content inside explicit passive data delimiters (`<external_data>...</external_data>`) and instruct the system prompt never to follow directives inside data tags.

3. **Missing System and User Role Separation**
   - **Risk**: Merging system rules and user input into a single flat string weakens instruction hierarchy.
   - **Remediation**: Always pass system rules in a dedicated `system` role message and untrusted input in a separate `user` role message.

4. **Unvalidated Tool Invocations**
   - **Risk**: Executing tools directly from raw LLM text or external arguments enables command injection, SSRF, or unauthorized actions.
   - **Remediation**: Validate tool names against an explicit allowlist, parse arguments against a strict Pydantic schema, and inspect tool calls via `RuntimeSecurityMonitor.inspect_tool_call()`.
