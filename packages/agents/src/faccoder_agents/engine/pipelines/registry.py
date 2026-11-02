from __future__ import annotations

from typing import Any

from faccoder_agents.engine.graph import PipelineGraph
from faccoder_agents.engine.pipelines.models import PipelineTemplate
from faccoder_agents.engine.pipelines.templates import (
    create_bugfix_pipeline,
    create_documentation_pipeline,
    create_feature_pipeline,
    create_legacy_migration_pipeline,
    create_refactor_pipeline,
    create_security_audit_pipeline,
)

_REGISTRY: dict[str, PipelineTemplate] = {}


def register_pipeline_template(template: PipelineTemplate) -> None:
    """Register a new ready-made pipeline template."""
    _REGISTRY[template.name] = template


def get_pipeline_template(name: str) -> PipelineTemplate:
    """Retrieve a registered pipeline template by name."""
    if not _REGISTRY:
        _init_default_templates()
    if name not in _REGISTRY:
        raise KeyError(f"Pipeline template '{name}' not found. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def list_pipeline_templates(category: str | None = None) -> list[PipelineTemplate]:
    """List registered pipeline templates, optionally filtered by category."""
    if not _REGISTRY:
        _init_default_templates()
    templates = list(_REGISTRY.values())
    if category:
        templates = [t for t in templates if t.category == category]
    return templates


def build_pipeline(name: str, **kwargs: Any) -> PipelineGraph:
    """Build and compile a ready-made pipeline by name."""
    template = get_pipeline_template(name)
    return template.build(**kwargs)


def _init_default_templates() -> None:
    """Populate default ready-made templates."""
    defaults = [
        PipelineTemplate(
            name="feature-delivery",
            description="End-to-end feature delivery: validation, architecture design, codegen, committee, approval.",
            category="delivery",
            required_inputs=["feature_name", "user_story"],
            factory=create_feature_pipeline,
        ),
        PipelineTemplate(
            name="bugfix-delivery",
            description=(
                "Surgical defect resolution: incident triage, root-cause analysis, "
                "patch synthesis, committee, approval."
            ),
            category="maintenance",
            required_inputs=["issue_id", "description", "error_stack"],
            factory=create_bugfix_pipeline,
        ),
        PipelineTemplate(
            name="code-refactor",
            description=(
                "Structural refactoring: complexity audit, modularization planning, committee review, approval gate."
            ),
            category="maintenance",
            required_inputs=["target_module", "refactor_goal"],
            factory=create_refactor_pipeline,
        ),
        PipelineTemplate(
            name="security-audit",
            description=(
                "Threat modeling and security assessment: STRIDE analysis, "
                "security committee, remediation plan, approval."
            ),
            category="governance",
            required_inputs=["service_name", "attack_surface"],
            factory=create_security_audit_pipeline,
        ),
        PipelineTemplate(
            name="legacy-migration",
            description=(
                "Incremental legacy modernization: logic deconstruction, "
                "modern stack synthesis, parity audit, approval."
            ),
            category="migration",
            required_inputs=["legacy_source", "target_stack"],
            factory=create_legacy_migration_pipeline,
        ),
        PipelineTemplate(
            name="documentation",
            description=(
                "System documentation: architectural synthesis, API reference generation, publishing approval gate."
            ),
            category="documentation",
            required_inputs=["project_name", "source_scope"],
            factory=create_documentation_pipeline,
        ),
    ]

    for tmpl in defaults:
        _REGISTRY[tmpl.name] = tmpl
