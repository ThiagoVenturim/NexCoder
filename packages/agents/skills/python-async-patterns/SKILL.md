---
name: python-async-patterns
description: Patterns and rules for building resilient asynchronous Python applications with asyncio and anyio.
user-invocable: true
---

# Python Async Patterns

Engineering standards for non-blocking asynchronous Python services.

## Guidelines
1. **Never Block the Event Loop**:
   - Offload synchronous file I/O, heavy CPU computations, and legacy blocking libraries to thread pools using `asyncio.to_thread()` or executor pools.
   - Use asynchronous HTTP clients (`httpx.AsyncClient`) and async database drivers (`asyncpg`, `asyncmy`).
2. **Task Cancellation & Timeouts**:
   - Always wrap unbounded network operations in `asyncio.timeout()`:
   ```python
   async with asyncio.timeout(10.0):
       await client.fetch_data()
   ```
3. **Structured Concurrency**:
   - Use `asyncio.TaskGroup` (Python 3.11+) to guarantee deterministic error handling and child task cleanup.
