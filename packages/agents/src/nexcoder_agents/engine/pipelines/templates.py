from __future__ import annotations

from typing import Any

from nexcoder_agents.engine.blocks.approval import HumanApprovalBlock
from nexcoder_agents.engine.blocks.committee import CommitteeBlock, CommitteeMember
from nexcoder_agents.engine.blocks.guardrails import ExecutionLimits
from nexcoder_agents.engine.blocks.prompt import PromptBlock
from nexcoder_agents.engine.blocks.validator import ValidatorBlock
from nexcoder_agents.engine.graph import PipelineBuilder
from nexcoder_agents.software_engineering import SoftwareEngineeringAuditBlock


def create_feature_pipeline(
    name: str = "feature-delivery",
    approval_action: str = "deploy_feature",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build an end-to-end feature delivery pipeline."""
    builder = PipelineBuilder(name)

    # 1. Validate inputs
    val = ValidatorBlock(
        name="feature_validator",
        required_keys=["feature_name", "user_story"],
    )

    # 2. Technical design
    design = PromptBlock(
        name="technical_design",
        user_prompt_template=(
            "You are a principal software architect.\n"
            "Feature: {feature_name}\n"
            "User Story: {user_story}\n"
            "Draft a robust architectural design, data models, and edge-case checklist."
        ),
        output_key="technical_spec",
        tier="large",
        model=model,
    )

    # 3. Code implementation
    codegen = PromptBlock(
        name="code_generation",
        user_prompt_template=(
            "You are a senior full-stack engineer.\n"
            "Specification: {technical_spec}\n"
            "Produce the complete, idiomatic implementation adhering to clean architecture."
        ),
        output_key="implementation_code",
        tier="large",
        model=model,
    )

    # 4. Multi-agent review committee (b90)
    committee = CommitteeBlock(
        name="review_committee",
        members=[
            CommitteeMember(name="cto_juror", perspective="Technical Scalability and Architecture", weight=1.5),
            CommitteeMember(name="qa_juror", perspective="Testability and Regression Coverage", weight=1.0),
            CommitteeMember(name="sec_juror", perspective="Security Vulnerabilities and Access Control", weight=1.5),
        ],
        target_key="implementation_code",
        quorum_threshold=0.6,
        model=model,
    )

    # 5. Human approval gate (b85)
    gate = HumanApprovalBlock(
        name="feature_gate",
        action_name=approval_action,
        description="Approve feature release and production deployment",
        payload_keys=["feature_name", "technical_spec"],
    )

    builder.add_sequence([val, design, codegen, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_bugfix_pipeline(
    name: str = "bugfix-delivery",
    approval_action: str = "merge_fix",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build a surgical bug investigation and resolution pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="incident_validator",
        required_keys=["issue_id", "description", "error_stack"],
    )

    rca = PromptBlock(
        name="root_cause_analysis",
        user_prompt_template=(
            "You are a site reliability engineer.\n"
            "Issue: {issue_id}\n"
            "Description: {description}\n"
            "Stack Trace: {error_stack}\n"
            "Diagnose the exact root cause, faulty assumptions, and failure mechanism."
        ),
        output_key="root_cause",
        tier="medium",
        model=model,
    )

    fix = PromptBlock(
        name="patch_synthesis",
        user_prompt_template=(
            "You are a senior bugfix specialist.\n"
            "Root Cause: {root_cause}\n"
            "Generate a minimal, surgical patch and targeted regression test."
        ),
        output_key="patch_code",
        tier="medium",
        model=model,
    )

    committee = CommitteeBlock(
        name="bugfix_committee",
        members=[
            CommitteeMember(name="qa_juror", perspective="Regression Coverage and Edge Cases", weight=1.0),
            CommitteeMember(name="eng_juror", perspective="Minimal Surgical Intervention", weight=1.0),
        ],
        target_key="patch_code",
        quorum_threshold=0.6,
        model=model,
    )

    gate = HumanApprovalBlock(
        name="bugfix_gate",
        action_name=approval_action,
        description="Approve bugfix patch merge",
        payload_keys=["issue_id", "patch_code"],
    )

    builder.add_sequence([val, rca, fix, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_refactor_pipeline(
    name: str = "code-refactor",
    approval_action: str = "apply_refactoring",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build a code refactoring and modularization pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="refactor_validator",
        required_keys=["target_module", "refactor_goal"],
    )

    audit = PromptBlock(
        name="complexity_audit",
        user_prompt_template=(
            "You are a code quality specialist.\n"
            "Target Module: {target_module}\n"
            "Goal: {refactor_goal}\n"
            "Analyze cyclomatic complexity, coupling, and identify monolithic anti-patterns."
        ),
        output_key="audit_findings",
        tier="medium",
        model=model,
    )

    plan = PromptBlock(
        name="refactoring_plan",
        user_prompt_template=(
            "You are a software architect.\n"
            "Audit Findings: {audit_findings}\n"
            "Formulate a step-by-step modularization plan preserving public interfaces."
        ),
        output_key="refactoring_steps",
        tier="large",
        model=model,
    )

    committee = CommitteeBlock(
        name="refactor_committee",
        members=[
            CommitteeMember(name="arch_juror", perspective="Interface Preservation and Compatibility", weight=1.2),
            CommitteeMember(name="test_juror", perspective="Testability and Code Simplicity", weight=1.0),
        ],
        target_key="refactoring_steps",
        quorum_threshold=0.6,
        model=model,
    )

    gate = HumanApprovalBlock(
        name="refactor_gate",
        action_name=approval_action,
        description="Approve refactoring code modifications",
        payload_keys=["target_module", "refactoring_steps"],
    )

    builder.add_sequence([val, audit, plan, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_security_audit_pipeline(
    name: str = "security-audit",
    approval_action: str = "signoff_security_audit",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build a threat modeling and security posture evaluation pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="scope_validator",
        required_keys=["service_name", "attack_surface"],
    )

    threat = PromptBlock(
        name="threat_model",
        user_prompt_template=(
            "You are a senior application security engineer.\n"
            "Service: {service_name}\n"
            "Attack Surface: {attack_surface}\n"
            "Perform STRIDE threat modeling and map potential vulnerability vectors."
        ),
        output_key="threat_analysis",
        tier="large",
        model=model,
    )

    committee = CommitteeBlock(
        name="security_committee",
        members=[
            CommitteeMember(name="ciso_juror", perspective="Risk Severity and Attack Surface", weight=1.5),
            CommitteeMember(name="compliance_juror", perspective="Regulatory and Data Privacy Adherence", weight=1.0),
        ],
        target_key="threat_analysis",
        quorum_threshold=0.6,
        model=model,
    )

    remediation = PromptBlock(
        name="remediation_plan",
        user_prompt_template=(
            "You are a security remediation specialist.\n"
            "Threats: {threat_analysis}\n"
            "Provide prioritized remediation directives with code-level hardening guidance."
        ),
        output_key="remediation_tasks",
        tier="medium",
        model=model,
    )

    gate = HumanApprovalBlock(
        name="security_gate",
        action_name=approval_action,
        description="Sign off security audit findings and approved remediation plan",
        payload_keys=["service_name", "remediation_tasks"],
    )

    builder.add_sequence([val, threat, committee, remediation, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_legacy_migration_pipeline(
    name: str = "legacy-migration",
    approval_action: str = "commit_migration_slice",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build an incremental legacy modernization and migration pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="migration_validator",
        required_keys=["legacy_source", "target_stack"],
    )

    analyze = PromptBlock(
        name="legacy_analysis",
        user_prompt_template=(
            "You are a legacy migration specialist.\n"
            "Legacy Source:\n{legacy_source}\n"
            "Target Stack: {target_stack}\n"
            "Deconstruct the legacy logic, data schemas, side-effects, and implicit state."
        ),
        output_key="deconstructed_logic",
        tier="large",
        model=model,
    )

    synthesize = PromptBlock(
        name="modern_target_synthesis",
        user_prompt_template=(
            "You are a modern software engineer in {target_stack}.\n"
            "Logic Specification: {deconstructed_logic}\n"
            "Write the equivalent modern implementation using idiomatic patterns."
        ),
        output_key="modern_code",
        tier="large",
        model=model,
    )

    committee = CommitteeBlock(
        name="migration_committee",
        members=[
            CommitteeMember(name="parity_juror", perspective="Business Logic Parity", weight=1.5),
            CommitteeMember(name="modern_stack_juror", perspective="Idiomatic Target Conventions", weight=1.0),
        ],
        target_key="modern_code",
        quorum_threshold=0.6,
        model=model,
    )

    gate = HumanApprovalBlock(
        name="migration_gate",
        action_name=approval_action,
        description="Approve modernized code slice migration",
        payload_keys=["target_stack", "modern_code"],
    )

    builder.add_sequence([val, analyze, synthesize, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_documentation_pipeline(
    name: str = "documentation-pipeline",
    approval_action: str = "publish_docs",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build an automated architectural and symbol documentation pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="doc_validator",
        required_keys=["project_name", "source_scope"],
    )

    arch_doc = PromptBlock(
        name="architecture_summary",
        user_prompt_template=(
            "You are a technical writer and systems architect.\n"
            "Project: {project_name}\n"
            "Scope: {source_scope}\n"
            "Synthesize a clear architecture overview, module boundaries, and interactions."
        ),
        output_key="architecture_doc",
        tier="medium",
        model=model,
    )

    api_doc = PromptBlock(
        name="api_docgen",
        user_prompt_template=(
            "You are an API documentation expert.\n"
            "Architecture Context: {architecture_doc}\n"
            "Scope: {source_scope}\n"
            "Generate comprehensive API documentation with contract descriptions and examples."
        ),
        output_key="api_documentation",
        tier="medium",
        model=model,
    )

    gate = HumanApprovalBlock(
        name="doc_gate",
        action_name=approval_action,
        description="Approve technical documentation for publication",
        payload_keys=["project_name", "architecture_doc", "api_documentation"],
    )

    builder.add_sequence([val, arch_doc, api_doc, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def create_software_engineering_pipeline(
    name: str = "software-engineering-review",
    approval_action: str = "approve_architecture_and_refactoring",
    limits: ExecutionLimits | None = None,
    model: Any = None,
) -> PipelineBuilder:
    """Build an end-to-end software engineering review, ADR, planning, and guided refactoring pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="engsw_validator",
        required_keys=["project_name", "architecture_goal"],
    )

    audit_block = SoftwareEngineeringAuditBlock(
        name="software_engineering_audit",
        llm=model,
    )

    opinion = PromptBlock(
        name="architecture_opinion",
        user_prompt_template=(
            "You are a principal software architect.\n"
            "Project: {project_name}\n"
            "Goal: {architecture_goal}\n"
            "Assessment: {architecture_assessment}\n"
            "Synthesize an executive architecture opinion, pattern trade-offs, and ADR recommendations."
        ),
        output_key="architecture_opinion_summary",
        tier="large",
        model=model,
    )

    committee = CommitteeBlock(
        name="architecture_committee",
        members=[
            CommitteeMember(name="lead_architect", perspective="Clean Boundaries and Pattern Fit", weight=1.5),
            CommitteeMember(name="qa_lead", perspective="Testing Pyramid and Refactoring Safety", weight=1.2),
            CommitteeMember(name="cto_juror", perspective="Pragmatic Trade-offs and Delivery Velocity", weight=1.0),
        ],
        target_key="architecture_opinion_summary",
        quorum_threshold=0.6,
        model=model,
    )

    gate = HumanApprovalBlock(
        name="engsw_gate",
        action_name=approval_action,
        description="Approve architecture review, ADRs, prioritized backlog, and guided refactoring",
        payload_keys=["project_name", "architecture_opinion_summary", "prioritized_actions"],
    )

    builder.add_sequence([val, audit_block, opinion, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder
