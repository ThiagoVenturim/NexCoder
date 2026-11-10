---
name: clean-architecture
description: Enforce Clean Architecture and Hexagonal boundaries, dependency inversion, pure domain models, and explicit ports and adapters.
user-invocable: true
---

# Clean Architecture

Rules for structuring domain-centric software with strict dependency inversion and testable boundaries.

## Core Principles

1. **The Dependency Rule**
   - Source code dependencies must point strictly inward toward higher-level policies.
   - Domain entities and value objects must have zero dependencies on ORMs, web frameworks, CLI parsers, or external SDKs.

2. **Explicit Ports and Adapters**
   - Define repository and gateway interfaces (Protocols or ABCs) inside the domain or application layer.
   - Implement concrete storage, network, and filesystem adapters in outer infrastructure modules.

3. **Pure Domain Services**
   - Keep business rules deterministic and side-effect free wherever possible.
   - Pass time, random seeds, and external state explicitly rather than reading global state inside domain logic.
