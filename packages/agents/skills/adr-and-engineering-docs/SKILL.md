---
name: adr-and-engineering-docs
description: Author Architecture Decision Records (ADRs), Mermaid system diagrams, and bottom-up code documentation synthesized from AST symbols.
user-invocable: true
---

# ADRs and Engineering Documentation

Standards for maintaining living engineering documentation synchronized with codebase structure.

## 1. Architecture Decision Records (ADR)
Record every significant architectural, pattern, or dependency decision in a structured markdown document:
- **ID & Title**: Sequential identifier (e.g., `ADR-001: Adopt Hexagonal Repository Boundary`).
- **Status**: `Proposed`, `Accepted`, `Deprecated`, or `Superseded`.
- **Context**: Technical forces, constraints, and problem statement driving the decision.
- **Decision**: Concrete architectural pattern, contract, or constraint adopted.
- **Consequences**: Positive outcomes, accepted trade-offs, and follow-up actions.
- **Alternatives Considered**: Options evaluated and reasons they were rejected.

## 2. Architecture Diagrams
- Express module dependencies, layer boundaries, and data flows using Mermaid `flowchart TD` or `sequenceDiagram` blocks.
- Quote node labels containing parentheses or special characters to guarantee valid rendering.

## 3. Bottom-Up Documentation Synthesis
- Roll up documentation hierarchically from AST symbols using `nexcoder-code-intel`:
  - **Level 0 (Routine)**: Function/method signatures, parameters, return types, and behavior summaries.
  - **Level 1 (Class)**: State encapsulation and member routine catalog.
  - **Level 2 (Module)**: Exported classes, standalone functions, and module dependencies.
  - **Level 3 (System)**: High-level subsystem clusters and module index.
