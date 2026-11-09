from __future__ import annotations

import json

from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_ideation.intake import IdeaAnalyst
from nexcoder_ideation.models import RawIdea, StructuredIdea


def test_heuristic_intake() -> None:
    analyst = IdeaAnalyst()
    raw = (
        "Autonomous security compliance scanning tool for Kubernetes clusters that generates "
        "remediation pull requests automatically."
    )
    structured = analyst.analyze(raw)

    assert isinstance(structured, StructuredIdea)
    assert len(structured.title) > 0
    assert "cybersecurity" in structured.domain_tags
    assert len(structured.target_audience) >= 1
    assert structured.value_hypothesis.problem_statement != ""
    assert len(structured.initial_assumptions) >= 1


def test_model_based_intake_with_fake_model() -> None:
    fake_response = {
        "title": "KubeFix Agent",
        "summary": "Autonomous Kubernetes compliance and remediation engine.",
        "problem": "Manual cluster hardening is error-prone and tedious for DevOps teams.",
        "target_audience": [
            {
                "name": "DevSecOps Engineers",
                "description": "Engineers responsible for cloud infrastructure security.",
                "pain_points": ["Audit compliance friction", "Manual manifest patching"],
                "willingness_to_pay": "high",
            }
        ],
        "value_hypothesis": {
            "problem_statement": "Audit findings accumulate faster than teams can patch them.",
            "proposed_solution": "Agent that detects misconfigurations and opens validated fix PRs.",
            "key_benefit": "Zero-touch compliance remediation in under 5 minutes.",
            "differentiation_summary": "Active PR creation instead of passive alert dashboards.",
            "primary_metric": "Mean Time to Remediate (MTTR) reduced by 85%",
        },
        "domain_tags": ["devops", "cybersecurity", "kubernetes"],
        "initial_assumptions": [
            "Teams grant GitHub App write permissions for PR creation.",
            "Cluster read access can be granted securely via ServiceAccount.",
        ],
    }

    fake_model = FakeChatModel(responses=[json.dumps(fake_response)])
    analyst = IdeaAnalyst(model=fake_model)

    raw_idea = RawIdea(
        raw_text="Kubernetes security bot that opens PRs to fix security issues.",
        author="alice",
    )
    result = analyst.analyze(raw_idea)

    assert result.title == "KubeFix Agent"
    assert "cybersecurity" in result.domain_tags
    assert result.target_audience[0].name == "DevSecOps Engineers"
    assert result.target_audience[0].willingness_to_pay == "high"
    assert "MTTR" in result.value_hypothesis.primary_metric
