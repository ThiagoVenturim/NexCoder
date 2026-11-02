---
name: rust-memory-guard
description: Guidelines and patterns for memory safety, borrowing semantics, and safe concurrency in Rust.
user-invocable: true
---

# Rust Memory Guard

This skill defines mandatory patterns for writing memory-safe, high-concurrency Rust code.

## 1. Zero Unsafe Policy
- Do not introduce `unsafe` blocks for convenience.
- When `unsafe` is strictly required for C FFI or performance-critical primitives:
  - Document the exact safety invariant required.
  - Wrap the unsafe block in a safe public abstraction.
  - Write exhaustive miri tests verifying absence of undefined behavior.

## 2. Ownership and Lifetime Discipline
- Avoid unnecessary cloning; design around references (`&T`, `&mut T`).
- Prefer standard smart pointers (`Arc<T>`, `Mutex<T>`, `RwLock<T>`) for shared state across threads.
- Prevent lock poisoning and deadlocks by acquiring locks in deterministic hierarchical orders and keeping critical sections minimal.

## 3. Error Handling
- Never use `.unwrap()` or `.expect()` in production paths; use the `?` operator.
- Structure domain errors using `thiserror` for library boundaries and `anyhow` for top-level application runners.
