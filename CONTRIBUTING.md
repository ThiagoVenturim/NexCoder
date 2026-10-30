# Contributing to faccoder

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
  preset (`FaccoderConfig(preset="offline")`) or `FakeChatModel` in tests.
- Model calls go through `faccoder_core.get_chat_model(tier)`; never hardcode a
  vendor model in a package.
- No secrets or real personal data in code, tests or fixtures.

## Commit messages

Conventional commits in English: `feat(code-intel): add COBOL paragraph parser`,
`fix(core): handle empty FTS query`, `docs: explain reranking`. Keep commits small.

## Packages

Each package lives in `packages/<name>/` with its own `pyproject.toml`, `src/`,
`tests/` and `README.md`, and depends on `faccoder-core`.
