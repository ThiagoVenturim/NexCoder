# Contributing to nexcoder

Thank you for helping. A few rules keep the project consistent.

## Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -e packages/core ruff pytest   # Windows: .venv\Scripts\python
git config core.hooksPath .githooks
```

The hooks block emojis and strip AI co-author trailers from commit messages.

## Before opening a pull request

- `python scripts/check_no_emoji.py` passes. The project uses no emojis in code,
  documentation, UI strings or commit messages.
- `ruff check packages scripts` passes.
- `python -m pytest packages` passes without network access. Use the `offline`
  preset (`NexcoderConfig(preset="offline")`) or `FakeChatModel` in tests.
- Model calls go through `nexcoder_core.get_chat_model(tier)`; never hardcode a
  vendor model in a package.
- No secrets or real personal data in code, tests or fixtures.

## Commit messages

Conventional commits in English: `feat(code-intel): add COBOL paragraph parser`,
`fix(core): handle empty FTS query`, `docs: explain reranking`. Keep commits small.

## Packages

Each package lives in `packages/<name>/` with its own `pyproject.toml`, `src/`,
`tests/` and `README.md`, and depends on `nexcoder-core`.

## How to contribute

1. Fork the repository and clone your fork.
2. Create a branch from `develop` (`feat/short-name`, `fix/short-name`, `docs/short-name`).
3. Commit small changes with conventional commit messages in English.
4. Open a pull request against `develop`, never against `main`, and fill in the template.
5. Continuous integration must pass and the maintainer must approve
   (`.github/CODEOWNERS`). Reviews may be assisted by an AI reviewer; the final
   approval is always human.
6. Pull requests are squash-merged into `develop`. The maintainer releases
   `develop` into `main` through a release pull request.

Branches `main` and `develop` are protected: no direct pushes, no force pushes and
no deletion. Pull requests from forks run CI only after the maintainer approves
the workflow run.

Security issues: see `SECURITY.md`. Conduct: see `CODE_OF_CONDUCT.md`.
