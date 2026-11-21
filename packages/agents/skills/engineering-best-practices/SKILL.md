---
name: engineering-best-practices
description: Audit and enforce software engineering practices across testing pyramid, CI/CD pipelines, semantic versioning, conventional commits, and branch governance.
user-invocable: true
---

# Engineering Best Practices

Operational standards for reliable software delivery, test automation, versioning, and repository hygiene.

## 1. Testing Pyramid (Unit, Integration, End-to-End)
- **Unit Tests**: Fast, deterministic, offline tests covering domain models, edge cases, and boundary conditions without network or disk side effects.
- **Integration Tests**: Verify contracts across module boundaries, storage repositories, and serialization layers using local fixtures or in-memory stores.
- **End-to-End (E2E) Tests**: Validate complete user-facing workflows and CLI/API entrypoints from intake to output artifacts.
- Every public routine and service method must have corresponding automated test assertions.

## 2. Continuous Integration and Delivery (CI/CD)
- Every push and pull request must execute automated linting (`ruff check`), formatting verification, offline test suites (`pytest`), and secret scanning.
- Pipelines must fail fast on broken checks and avoid hidden network dependencies during unit test runs.

## 3. Semantic Versioning (SemVer)
- Follow `MAJOR.MINOR.PATCH` (`X.Y.Z`) versioning in package manifests:
  - `MAJOR`: incompatible API or contract changes.
  - `MINOR`: backward-compatible features and new capabilities.
  - `PATCH`: backward-compatible bug fixes and internal refactors.

## 4. Conventional Commits
- Format every commit message as `<type>(<scope>): <description>` in English:
  - Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`, `build`.
  - Keep commits atomic, focused on a single logical change, and free of emojis or AI co-author trailers.

## 5. Branch Organization
- `main`: production branch containing stable tagged releases only.
- `develop`: integration branch where reviewed features converge.
- `feat/<name>`, `fix/<name>`, `layer/<name>`: short-lived work branches merged into `develop` via pull requests after green CI checks.
