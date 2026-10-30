"""Path sandbox for tools that read or write files on behalf of an agent.

An agent asking for ``../../etc/passwd`` or an absolute path outside the
project must be refused before any I/O happens. Every file-access tool
resolves paths through ``resolve_inside``.
"""

from __future__ import annotations

from pathlib import Path


class PathOutsideSandboxError(PermissionError):
    pass


def resolve_inside(root: str | Path, requested: str | Path) -> Path:
    """Resolve ``requested`` relative to ``root`` and ensure it stays inside it.

    Symlinks are resolved first, so a link pointing outside the root is refused too.
    """
    base = Path(root).resolve()
    candidate = Path(requested)
    target = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if target != base and base not in target.parents:
        raise PathOutsideSandboxError(f"Access denied: '{requested}' is outside {base}")
    return target
