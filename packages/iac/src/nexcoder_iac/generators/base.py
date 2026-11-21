"""Base interface for all infrastructure-as-code generators."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexcoder_iac.models import ArchitectureSpec, IaCArtifacts


class BaseGenerator(ABC):
    """Abstract base generator producing deployable IaC artifacts from an ArchitectureSpec."""

    @abstractmethod
    def generate(self, spec: ArchitectureSpec) -> IaCArtifacts:
        """Generate all necessary files and instructions for the specified architecture."""
        raise NotImplementedError
