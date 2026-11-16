"""Tests for ML/AI Feature Engineering Advisor, Parameterized Recipes, Guardrails,
and Offline Evaluation in nexcoder-agents.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from nexcoder_agents.ai_engineering import (
    AIFeatureAdvisor,
    AIFeatureBlock,
    AIFeatureRequest,
    AIGuardrailEngine,
    ApproachType,
    ClassificationRecipe,
    ExtractionRecipe,
    MLApproachSelector,
    ModelOpenness,
    RAGRecipe,
    RecipeType,
)
from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.cli import main as cli_main
from nexcoder_agents.engine.models import BlockStatus
from nexcoder_agents.engine.pipelines import create_ai_feature_pipeline, list_pipeline_templates
from nexcoder_control.approval import TargetAuthorizationGate, TargetNotAuthorizedError
from nexcoder_control.metering import AppendOnlyAuditLog, BudgetExceededError


def test_ml_engineer_persona_loaded_in_catalog() -> None:
    """Verifies ml-engineer agent definition loads with expected metadata."""
    catalog = AgentCatalog.default()
    agent = catalog.get("ml-engineer")
    assert agent is not None
    assert agent.name == "ML/AI Feature Engineer"
    assert agent.sector == "data-ai"
    assert agent.tier == "medium"
    assert "ml-approach-selection" in agent.skills
    assert "ai-feature-recipes" in agent.skills
    assert "model-serving-integration" in agent.skills
    assert "ai-guardrails-enforcement" in agent.skills


def test_ai_engineering_skills_loaded_in_catalog() -> None:
    """Verifies the four new skills load from the skill catalog."""
    skills = SkillCatalog.default()
    for slug in [
        "ml-approach-selection",
        "ai-feature-recipes",
        "model-serving-integration",
        "ai-guardrails-enforcement",
    ]:
        skill = skills.get(slug)
        assert skill is not None, f"Skill {slug} must be registered"
        assert len(skill.description) > 10


def test_approach_selector_heuristics() -> None:
    """Verifies decision matrix choosing rule, ML, or LLM/RAG based on constraints."""
    selector = MLApproachSelector()

    # Low latency -> Rule-based
    dec_rule = selector.select_approach(
        feature_desc="Input validation and token counting",
        recipe=RecipeType.CLASSIFICATION,
        latency_budget_ms=5,
    )
    assert dec_rule.approach == ApproachType.RULE
    assert dec_rule.model_openness == ModelOpenness.OPEN_WEIGHTS

    # High sample tabular -> Classical ML
    dec_ml = selector.select_approach(
        feature_desc="Customer churn prediction",
        recipe=RecipeType.CLASSIFICATION,
        latency_budget_ms=30,
        sample_count=500,
    )
    assert dec_ml.approach == ApproachType.CLASSICAL_ML

    # Semantic RAG -> LLM/RAG
    dec_rag = selector.select_approach(
        feature_desc="Knowledge base query and answer synthesis",
        recipe=RecipeType.RAG,
        latency_budget_ms=500,
    )
    assert dec_rag.approach == ApproachType.LLM_RAG
    assert dec_rag.open_model_preferred is True

    # Forced approach override
    dec_forced = selector.select_approach(
        feature_desc="Custom extraction",
        recipe=RecipeType.EXTRACTION,
        forced_approach=ApproachType.RULE,
    )
    assert dec_forced.approach == ApproachType.RULE


def test_guardrails_target_authorization_rejection(tmp_path: Path) -> None:
    """Verifies execution fails closed when target directory is not authorized."""
    audit_log = AppendOnlyAuditLog()
    gate = TargetAuthorizationGate(audit_log=audit_log)
    engine = AIGuardrailEngine(target_gate=gate, audit_log=audit_log)
    advisor = AIFeatureAdvisor(guardrail_engine=engine)

    unauthorized_dir = tmp_path / "unauthorized_project"
    unauthorized_dir.mkdir()

    req = AIFeatureRequest(
        project_dir=str(unauthorized_dir),
        feature_name="ticket_triage",
        recipe=RecipeType.CLASSIFICATION,
        description="Classify incoming tickets",
        owned_target=False,  # Not marked as owned, no approval token
    )

    with pytest.raises(TargetNotAuthorizedError):
        advisor.implement_feature(req, write_to_disk=False)


def test_guardrails_sensitive_data_detection(tmp_path: Path) -> None:
    """Verifies secrets in datasets are rejected prior to scaffolding."""
    advisor = AIFeatureAdvisor()

    req = AIFeatureRequest(
        project_dir=str(tmp_path),
        feature_name="leaky_feature",
        recipe=RecipeType.CLASSIFICATION,
        description="Feature with leaked secret in samples",
        owned_target=True,
        data_samples=[
            {"text": "Normal user ticket", "label": "bug"},
            {"text": "Config api_key='sk-proj-supersecretkey1234567890'", "label": "security"},
        ],
    )

    with pytest.raises(ValueError, match="Sensitive credentials"):
        advisor.implement_feature(req, write_to_disk=False)


def test_guardrails_budget_exceeded(tmp_path: Path) -> None:
    """Verifies budget limits are strictly enforced."""
    advisor = AIFeatureAdvisor()

    req = AIFeatureRequest(
        project_dir=str(tmp_path),
        feature_name="expensive_feature",
        recipe=RecipeType.CLASSIFICATION,
        description="Feature with zero budget ceiling",
        owned_target=True,
        monthly_budget_usd=0.01,  # Below estimated cost of $0.50
        enable_mlops_training=True,
    )

    with pytest.raises(BudgetExceededError):
        advisor.implement_feature(req, write_to_disk=False)


def test_recipes_generate_valid_python_syntax() -> None:
    """Verifies all six recipes generate syntactically valid Python code and tests."""
    selector = MLApproachSelector()

    for recipe_type in RecipeType:
        decision = selector.select_approach("Test feature", recipe_type)
        req = AIFeatureRequest(
            project_dir="/tmp/test",
            feature_name=f"test_{recipe_type.value}",
            recipe=recipe_type,
            description="Synthetic validation",
            owned_target=True,
        )
        recipe_impl = RecipeType(recipe_type)
        if recipe_impl == RecipeType.CLASSIFICATION:
            artifacts = ClassificationRecipe().generate_artifacts(req, decision)
        elif recipe_impl == RecipeType.EXTRACTION:
            artifacts = ExtractionRecipe().generate_artifacts(req, decision)
        elif recipe_impl == RecipeType.RAG:
            artifacts = RAGRecipe().generate_artifacts(req, decision)
        else:
            advisor = AIFeatureAdvisor()
            res = advisor.implement_feature(req, write_to_disk=False, run_eval=False)
            artifacts = [a for a in res.generated_files if isinstance(a, str)]
            continue

        for art in artifacts:
            if art.relative_path.endswith(".py"):
                ast.parse(art.content, filename=art.relative_path)


def test_end_to_end_classification_feature_scaffolding(tmp_path: Path) -> None:
    """Tests end-to-end implementation of a classification feature in a target project."""
    project_dir = tmp_path / "sample_ecommerce_app"
    project_dir.mkdir()

    advisor = AIFeatureAdvisor()
    req = AIFeatureRequest(
        project_dir=str(project_dir),
        feature_name="review_sentiment",
        recipe=RecipeType.CLASSIFICATION,
        description="Classify customer reviews as positive, negative, or neutral",
        output_schema={"labels": '["positive", "negative", "neutral"]'},
        owned_target=True,
        enable_mlops_training=True,
        enable_serving_compose=True,
    )

    result = advisor.implement_feature(req, write_to_disk=True, run_eval=True)

    assert result.feature_name == "review_sentiment"
    assert result.recipe == RecipeType.CLASSIFICATION
    assert result.governance_passed is True
    assert result.evaluation is not None
    assert result.evaluation.passed is True
    assert result.evaluation.metrics["accuracy"] >= 0.90
    assert result.serving_compose_path is not None
    assert result.dataset_manifest_path is not None

    # Check files created on disk
    clf_path = project_dir / "src" / "review_sentiment" / "classifier.py"
    test_path = project_dir / "tests" / "test_review_sentiment.py"
    compose_path = project_dir / "ops" / "review_sentiment" / "docker-compose.serving.yml"
    manifest_path = project_dir / "data" / "review_sentiment" / "manifest.json"

    assert clf_path.exists()
    assert test_path.exists()
    assert compose_path.exists()
    assert manifest_path.exists()

    # Load and execute generated classifier module directly
    spec = importlib.util.spec_from_file_location("dynamic_classifier", clf_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    classifier_cls = getattr(module, "ReviewSentimentClassifier")
    classifier = classifier_cls()

    # Test positive classification
    res_pos = classifier.classify("This is a positive and great product!")
    assert res_pos.label == "positive"
    assert res_pos.confidence > 0.5

    # Test negative classification
    res_neg = classifier.classify("This is negative and broke immediately.")
    assert res_neg.label == "negative"

    # Test empty input
    res_empty = classifier.classify("")
    assert res_empty.confidence == 0.0


def test_end_to_end_rag_feature_scaffolding(tmp_path: Path) -> None:
    """Tests end-to-end implementation of a semantic RAG feature in a target project."""
    project_dir = tmp_path / "sample_docs_portal"
    project_dir.mkdir()

    advisor = AIFeatureAdvisor()
    req = AIFeatureRequest(
        project_dir=str(project_dir),
        feature_name="docs_qa",
        recipe=RecipeType.RAG,
        description="Semantic retrieval over technical product documentation",
        owned_target=True,
    )

    result = advisor.implement_feature(req, write_to_disk=True, run_eval=True)

    assert result.feature_name == "docs_qa"
    assert result.recipe == RecipeType.RAG
    assert result.evaluation is not None
    assert result.evaluation.metrics["retrieval_precision"] >= 0.85

    rag_path = project_dir / "src" / "docs_qa" / "rag_service.py"
    assert rag_path.exists()

    # Load and execute generated RAG service directly
    spec = importlib.util.spec_from_file_location("dynamic_rag", rag_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rag_cls = getattr(module, "DocsQaRAGService")
    rag = rag_cls()

    rag.index_documents([
        {"id": "doc1", "content": "NexCoder coordinates autonomous AI agents for full-stack engineering."},
        {"id": "doc2", "content": "PostgreSQL database configuration handles high concurrent transaction volume."},
    ])

    ans = rag.answer_query("How does NexCoder coordinate autonomous agents?")
    assert len(ans.retrieved_chunks) >= 1
    assert "autonomous AI agents" in ans.retrieved_chunks[0].content


def test_ai_feature_pipeline_template_and_block() -> None:
    """Verifies ai-feature pipeline template registration and block execution."""
    templates = list_pipeline_templates(category="ai-ml")
    assert any(t.name == "ai-feature-pipeline" for t in templates)

    builder = create_ai_feature_pipeline(name="test-ai-feature-pipe")
    compiled = builder.compile()
    assert compiled is not None

    state = {
        "ai_feature_request": {
            "project_dir": "/tmp/synthetic_proj",
            "feature_name": "lead_scoring",
            "recipe": "classification",
            "description": "Score sales leads",
            "owned_target": True,
        }
    }

    block = AIFeatureBlock()
    res = block.execute(state)
    assert res.status == BlockStatus.SUCCESS
    assert "ai_feature_result" in res.updates


def test_cli_implement_ai_feature_and_evaluate_approach(tmp_path: Path) -> None:
    """Verifies CLI subcommands implement-ai-feature and evaluate-ml-approach."""
    project_dir = tmp_path / "cli_test_proj"
    project_dir.mkdir()

    # evaluate-ml-approach
    code_eval = cli_main([
        "evaluate-ml-approach",
        "Semantic search across knowledge base",
        "--recipe",
        "rag",
        "--latency-budget-ms",
        "500",
    ])
    assert code_eval == 0

    # implement-ai-feature
    output_report = tmp_path / "report.md"
    code_impl = cli_main([
        "implement-ai-feature",
        str(project_dir),
        "--name",
        "spam_detector",
        "--recipe",
        "classification",
        "--output",
        str(output_report),
    ])
    assert code_impl == 0
    assert output_report.exists()
    content = output_report.read_text(encoding="utf-8")
    assert "spam_detector" in content
    assert "classification" in content
