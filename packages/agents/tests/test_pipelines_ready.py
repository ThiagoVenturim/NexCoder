from __future__ import annotations

import pytest
from faccoder_agents.catalog.registry import AgentCatalog
from faccoder_agents.catalog.skills import SkillCatalog
from faccoder_agents.cli import main
from faccoder_agents.engine.models import ApprovalStatus
from faccoder_agents.engine.pipelines import (
    build_pipeline,
    get_pipeline_template,
    list_pipeline_templates,
)
from faccoder_core.llm.fake import FakeChatModel


def test_new_stack_and_jury_personas_in_catalog() -> None:
    catalog = AgentCatalog.default()

    # 1. New stacks
    rust_agent = catalog.get("rust-engineer")
    assert rust_agent is not None
    assert rust_agent.sector == "stacks"
    assert "cargo" in rust_agent.tools
    assert "rust-memory-guard" in rust_agent.skills

    kotlin_agent = catalog.get("kotlin-engineer")
    assert kotlin_agent is not None
    assert kotlin_agent.sector == "stacks"

    php_agent = catalog.get("php-engineer")
    assert php_agent is not None
    assert php_agent.sector == "stacks"

    # 2. Jury personas
    investor = catalog.get("investor-juror")
    assert investor is not None
    assert investor.sector == "jury"

    cto = catalog.get("cto-juror")
    assert cto is not None
    assert cto.sector == "jury"

    security = catalog.get("security-officer-juror")
    assert security is not None
    assert security.sector == "jury"


def test_new_standard_skills() -> None:
    skills = SkillCatalog.default()
    rust_skill = skills.get("rust-memory-guard")
    assert rust_skill is not None
    assert "Zero Unsafe" in rust_skill.content

    threat_skill = skills.get("security-threat-model")
    assert threat_skill is not None
    assert "STRIDE" in threat_skill.content


def test_list_and_get_pipeline_templates() -> None:
    templates = list_pipeline_templates()
    assert len(templates) >= 6
    names = {t.name for t in templates}
    assert "feature-delivery" in names
    assert "bugfix-delivery" in names
    assert "code-refactor" in names
    assert "security-audit" in names
    assert "legacy-migration" in names
    assert "documentation" in names

    # Filter by category
    delivery = list_pipeline_templates(category="delivery")
    assert len(delivery) >= 1
    assert delivery[0].name == "feature-delivery"

    tmpl = get_pipeline_template("feature-delivery")
    assert tmpl.name == "feature-delivery"
    assert "feature_name" in tmpl.required_inputs

    with pytest.raises(KeyError):
        get_pipeline_template("non-existent-pipeline")


def test_feature_pipeline_dry_run() -> None:
    fake_llm = FakeChatModel(responses=["Design drafted.", "Code implemented."])
    pipeline = build_pipeline("feature-delivery", model=fake_llm)
    res = pipeline.run(
        inputs={
            "feature_name": "TwoFactorAuth",
            "user_story": "As a user, I want 2FA via TOTP so my account is secure.",
        },
        dry_run=True,
    )
    assert res.status == "completed"
    assert res.approval is not None
    assert res.approval.status == ApprovalStatus.DRY_RUN
    assert len(res.history) == 5


def test_bugfix_pipeline_execution() -> None:
    fake_llm = FakeChatModel(responses=["Root cause found.", "Patch synthesized."])
    pipeline = build_pipeline("bugfix-delivery", model=fake_llm)

    # 1. Missing inputs fails validator
    res_err = pipeline.run(inputs={"issue_id": "BUG-101"})
    assert res_err.status == "failed"
    assert len(res_err.errors) > 0

    # 2. Complete inputs runs to approval gate
    res = pipeline.run(
        inputs={
            "issue_id": "BUG-101",
            "description": "NullPointer in payment processor",
            "error_stack": "at PaymentService.process(PaymentService.java:42)",
        }
    )
    assert res.status == "waiting_approval"
    assert res.approval is not None
    assert res.approval.action_name == "merge_fix"

    token = res.approval.token
    saved_approval = res.approval.to_state_dict()

    # 3. Resume with per-block token
    res_approved = pipeline.run(
        inputs={
            "issue_id": "BUG-101",
            "description": "NullPointer in payment processor",
            "error_stack": "at PaymentService.process(PaymentService.java:42)",
            "approval_token_bugfix_gate": token,
            "approval_bugfix_gate": saved_approval,
        }
    )
    assert res_approved.status == "completed"


def test_security_audit_pipeline() -> None:
    fake_llm = FakeChatModel(responses=["Threat model complete.", "Remediation directives drafted."])
    pipeline = build_pipeline("security-audit", model=fake_llm)
    res = pipeline.run(
        inputs={
            "service_name": "BillingGateway",
            "attack_surface": "Public REST API with webhook callbacks",
        },
        dry_run=True,
    )
    assert res.status == "completed"
    assert "threat_analysis" in res.data
    assert "remediation_tasks" in res.data


def test_legacy_migration_pipeline() -> None:
    fake_llm = FakeChatModel(responses=["Deconstructed logic.", "Synthesized target code."])
    pipeline = build_pipeline("legacy-migration", model=fake_llm)
    res = pipeline.run(
        inputs={
            "legacy_source": "procedure CalcTax; begin Total := Base * 1.15; end;",
            "target_stack": "Python / FastAPI",
        },
        dry_run=True,
    )
    assert res.status == "completed"
    assert "deconstructed_logic" in res.data
    assert "modern_code" in res.data


def test_documentation_pipeline() -> None:
    fake_llm = FakeChatModel(responses=["Architecture synthesized.", "API reference generated."])
    pipeline = build_pipeline("documentation", model=fake_llm)
    res = pipeline.run(
        inputs={
            "project_name": "faccoder",
            "source_scope": "packages/agents and packages/core",
        },
        dry_run=True,
    )
    assert res.status == "completed"
    assert "architecture_doc" in res.data
    assert "api_documentation" in res.data


def test_cli_pipeline_commands(capsys) -> None:
    # 1. list-pipelines
    code = main(["list-pipelines"])
    assert code == 0
    out = capsys.readouterr().out
    assert "feature-delivery" in out
    assert "bugfix-delivery" in out

    # 2. show-pipeline
    code_show = main(["show-pipeline", "feature-delivery"])
    assert code_show == 0
    show_out = capsys.readouterr().out
    assert "Pipeline: feature-delivery" in show_out
    assert "Required Inputs: feature_name, user_story" in show_out

    # 3. show-pipeline invalid
    code_invalid = main(["show-pipeline", "unknown-pipeline"])
    assert code_invalid == 1
