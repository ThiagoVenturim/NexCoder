from __future__ import annotations

from nexcoder_agents.engine.pipelines.models import PipelineTemplate
from nexcoder_agents.engine.pipelines.registry import (
    build_pipeline,
    get_pipeline_template,
    list_pipeline_templates,
    register_pipeline_template,
)
from nexcoder_agents.engine.pipelines.templates import (
    create_bugfix_pipeline,
    create_documentation_pipeline,
    create_feature_pipeline,
    create_legacy_migration_pipeline,
    create_refactor_pipeline,
    create_security_audit_pipeline,
)

__all__ = [
    "PipelineTemplate",
    "build_pipeline",
    "create_bugfix_pipeline",
    "create_documentation_pipeline",
    "create_feature_pipeline",
    "create_legacy_migration_pipeline",
    "create_refactor_pipeline",
    "create_security_audit_pipeline",
    "get_pipeline_template",
    "list_pipeline_templates",
    "register_pipeline_template",
]
