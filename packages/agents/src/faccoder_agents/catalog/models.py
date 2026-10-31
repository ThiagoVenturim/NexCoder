from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentTier = Literal["small", "medium", "large"]


class AgentSector:
    DIRECTION = "direction"
    REQUIREMENTS = "requirements"
    PRODUCT = "product"
    ENGINEERING = "engineering"
    UI_UX = "ui-ux"
    QA = "qa"
    SECURITY = "security"
    DATA_AI = "data-ai"
    SUPPORT = "support"
    MARKETING_GTM = "marketing-gtm"
    STACKS = "stacks"
    REGULATIONS = "regulations"

    ALL = [
        DIRECTION,
        REQUIREMENTS,
        PRODUCT,
        ENGINEERING,
        UI_UX,
        QA,
        SECURITY,
        DATA_AI,
        SUPPORT,
        MARKETING_GTM,
        STACKS,
        REGULATIONS,
    ]


class AgentSpec(BaseModel):
    name: str
    slug: str
    sector: str
    tier: AgentTier = "medium"
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    prompt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_path: Path | None = None

    def render_prompt(self, **kwargs: Any) -> str:
        """Render prompt with kwargs interpolation."""
        if not kwargs:
            return self.prompt
        try:
            return self.prompt.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Fall back to safe partial replacement
            result = self.prompt
            for key, val in kwargs.items():
                result = result.replace(f"{{{key}}}", str(val))
            return result
