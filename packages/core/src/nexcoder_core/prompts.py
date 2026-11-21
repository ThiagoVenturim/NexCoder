"""Versioned prompts stored as YAML.

Prompts live next to the code that uses them, in ``prompts/<name>.yaml``::

    version: 3
    description: Scores an idea against the jury rubric.
    system: |
      You are {persona}. ...
    user: |
      Idea:
      {idea}

Keeping prompts in files makes them reviewable in pull requests, diffable, and
traceable: the version is attached to every Langfuse trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    system: str
    user: str
    description: str = ""

    def render(self, **values: object) -> tuple[str, str]:
        """Return (system, user) with ``{placeholders}`` filled in."""
        return self.system.format_map(_Strict(values)), self.user.format_map(_Strict(values))

    def messages(self, **values: object) -> list[tuple[str, str]]:
        system, user = self.render(**values)
        return [("system", system), ("human", user)] if system else [("human", user)]


class _Strict(dict):
    def __missing__(self, key: str) -> str:
        raise KeyError(f"Prompt placeholder '{{{key}}}' was not provided")


@lru_cache(maxsize=256)
def load_prompt(directory: str | Path, name: str) -> Prompt:
    path = Path(directory) / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt '{name}' not found in {directory}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Prompt(
        name=name,
        version=int(data.get("version", 1)),
        system=str(data.get("system", "")),
        user=str(data.get("user", "{input}")),
        description=str(data.get("description", "")),
    )
