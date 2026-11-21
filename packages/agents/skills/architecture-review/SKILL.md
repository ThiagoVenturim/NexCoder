---
name: architecture-review
description: Evaluate software architecture patterns (layered, hexagonal, event-driven), trade-offs, module boundaries, and coupling metrics.
user-invocable: true
---

# Architecture Review

Structured methodology for selecting, reviewing, and evolving software architecture patterns.

## Pattern Selection & Trade-Off Matrix

1. **Layered Architecture (N-Tier)**
   - **Best for**: CRUD-centric applications, administrative portals, and rapid initial delivery with well-understood domain rules.
   - **Structure**: Presentation / API -> Application / Service -> Domain / Model -> Persistence / Storage.
   - **Trade-offs**: Simple mental model and low boilerplate, but prone to database-driven domain modeling and sinkhole anti-patterns if layer boundaries are bypassed.

2. **Hexagonal Architecture (Ports and Adapters)**
   - **Best for**: Core business domains with rich invariants, multiple external integrations, or long-term testability requirements.
   - **Structure**: Pure Domain Core surrounded by Inbound Ports (use cases) and Outbound Ports (interfaces), implemented by Infrastructure Adapters (DB, HTTP, CLI, messaging).
   - **Trade-offs**: High testability and infrastructure independence at the cost of interface and mapping overhead.

3. **Event-Driven Architecture (EDA)**
   - **Best for**: Decoupled subsystems, asynchronous workflows, high-throughput pipelines, and audit-heavy domains.
   - **Structure**: Producers emit immutable domain/integration events; consumers handle side effects idempotently.
   - **Trade-offs**: Temporal decoupling and horizontal scalability, balanced against eventual consistency, observability complexity, and duplicate-delivery handling.

4. **Modular Monolith**
   - **Best for**: Medium-to-large teams seeking strong domain boundaries without distributed-systems operational overhead.
   - **Structure**: Single deployment unit partitioned into vertical domain modules communicating strictly via public module contracts.
   - **Trade-offs**: Fast local refactoring and transactional simplicity, requiring strict static enforcement to prevent cross-module backdoor imports.

## Architectural Review Checklist

- **Dependency Direction**: Inner domain layers must never import outer infrastructure, transport, or UI modules.
- **Cohesion & Coupling**: Modules should exhibit high internal cohesion (related symbols grouped together) and low efferent coupling.
- **Blast Radius Control**: High-fan-in symbols must have stable signatures, explicit contracts, and comprehensive unit test coverage.
- **Explicit Trade-offs**: Every significant structural choice must document its context, alternatives, and operational consequences in an ADR.
