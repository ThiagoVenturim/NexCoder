"""Offline tests for code quality and architecture detectors, gated reviewer,
reusable skills, and the quality-review pipeline (Issue #80).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nexcoder_agents import (
    BranchInfo,
    ProjectSnapshot,
    QualityCategory,
    QualityReviewer,
    QualitySeverity,
    QualityThresholds,
    build_pipeline,
    detect_branch_issues,
    detect_data_modeling_issues,
    detect_duplicate_functions,
    detect_over_engineering,
    detect_performance_smells,
    detect_readability_issues,
    detect_structure_issues,
    get_pipeline_template,
    normalize_code_tokens,
    token_similarity,
)
from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.cli import main
from nexcoder_agents.engine.models import ApprovalStatus
from nexcoder_control.approval import TargetNotAuthorizedError
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_core.llm.fake import FakeChatModel


def _quality_sample_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "quality_sample"


def test_quality_sample_planted_findings() -> None:
    sample_dir = _quality_sample_dir()
    assert sample_dir.is_dir()

    audit_log = AppendOnlyAuditLog()
    reviewer = QualityReviewer(audit_log=audit_log)
    report = reviewer.review(
        sample_dir,
        owned_target=True,
        authorized_by="qa-lead",
        collect_branches=False,
    )

    assert report.project_name == "quality_sample"
    assert report.files_analyzed == 6
    assert report.symbols_analyzed >= 8
    assert report.ownership == "owned"
    assert report.authorized_by == "qa-lead"

    # Every finding must carry file:line, severity (P1/P2/P3), and a suggestion.
    for finding in report.findings:
        assert finding.file_path
        assert finding.line >= 1
        assert ":" in finding.location
        assert finding.severity in {QualitySeverity.P1, QualitySeverity.P2, QualitySeverity.P3}
        assert finding.suggestion.strip()

    by_rule_loc = {(f.rule, f.location): f for f in report.findings}

    # 1. Planted duplicate functions across shop/invoices.py and shop/orders.py
    dup = by_rule_loc[("duplicate-function", "shop/invoices.py:8")]
    assert dup.category == QualityCategory.DUPLICATION
    assert dup.severity == QualitySeverity.P2
    assert dup.symbol == "compute_invoice_amount"
    assert "shop/orders.py:6" in dup.related_locations

    # 2. Planted useless pass-through wrapper in shop/invoices.py
    wrapper = by_rule_loc[("pass-through-wrapper", "shop/invoices.py:24")]
    assert wrapper.category == QualityCategory.USELESS_WRAPPER
    assert wrapper.severity == QualitySeverity.P2
    assert wrapper.symbol == "fetch_order_total"
    assert "calculate_order_total" in wrapper.message

    # 3. Planted over-engineering (single-implementation abstraction) in shop/notifications.py
    over_eng = by_rule_loc[("single-implementation-abstraction", "shop/notifications.py:8")]
    assert over_eng.category == QualityCategory.OVER_ENGINEERING
    assert over_eng.severity == QualitySeverity.P2
    assert over_eng.symbol == "NotifierStrategy"
    assert "shop/notifications.py:16" in over_eng.related_locations

    # 4. Planted long & complex function in shop/report.py
    long_fn = by_rule_loc[("long-function", "shop/report.py:6")]
    assert long_fn.category == QualityCategory.READABILITY
    assert long_fn.severity == QualitySeverity.P2
    assert long_fn.symbol == "build_sales_report"

    complex_fn = by_rule_loc[("high-complexity", "shop/report.py:6")]
    assert complex_fn.category == QualityCategory.READABILITY
    assert complex_fn.severity == QualitySeverity.P1
    assert complex_fn.symbol == "build_sales_report"

    # 5. Planted temporary solutions (HACK and TODO) in shop/report.py
    hack = by_rule_loc[("temporary-marker", "shop/report.py:8")]
    assert hack.category == QualityCategory.TEMPORARY_SOLUTION
    assert hack.severity == QualitySeverity.P2

    todo = by_rule_loc[("temporary-marker", "shop/report.py:11")]
    assert todo.category == QualityCategory.TEMPORARY_SOLUTION
    assert todo.severity == QualitySeverity.P3

    # 6. Planted N+1 query in loop in shop/report.py
    n_plus_one = by_rule_loc[("query-in-loop", "shop/report.py:27")]
    assert n_plus_one.category == QualityCategory.PERFORMANCE
    assert n_plus_one.severity == QualitySeverity.P2

    # 7. Planted SQL data modeling flaws in db/schema.sql
    assert ("repeated-column-group", "db/schema.sql:6") in by_rule_loc
    assert ("foreign-key-without-index", "db/schema.sql:13") in by_rule_loc
    assert ("missing-primary-key", "db/schema.sql:17") in by_rule_loc
    kv = by_rule_loc[("key-value-in-relational", "db/schema.sql:25")]
    assert kv.severity == QualitySeverity.P3

    # 8. Planted leftover file in shop/orders_old.py
    leftover = by_rule_loc[("leftover-file-name", "shop/orders_old.py:1")]
    assert leftover.category == QualityCategory.STRUCTURE
    assert leftover.severity == QualitySeverity.P2

    # Priority ordering and Markdown rendering
    counts = report.severity_counts()
    assert counts["P1"] >= 1
    assert counts["P2"] >= 8
    assert counts["P3"] >= 2
    md = report.to_markdown()
    assert "# Code Quality Review: quality_sample" in md
    assert "## P1 - fix first" in md
    assert "## P2 - plan next" in md
    assert "## P3 - clean up when touching the code" in md
    assert "Suggestion:" in md


def test_over_engineering_and_duplication_variants() -> None:
    files = {
        "pkg/layers.py": (
            "from abc import ABC, abstractmethod\n\n"
            "class UnusedPort(ABC):\n"
            "    @abstractmethod\n"
            "    def run(self, payload: str) -> str:\n"
            "        raise NotImplementedError\n\n"
            "class HollowFacade:\n"
            "    def __init__(self, repo) -> None:\n"
            "        self.repo = repo\n"
            "    def fetch(self, item_id: int):\n"
            "        return self.repo.fetch(item_id)\n"
            "    def remove(self, item_id: int):\n"
            "        return self.repo.remove(item_id)\n\n"
            "class StatelessHelper:\n"
            "    def format_label(self, text: str) -> str:\n"
            "        return text.strip().upper()\n"
        ),
        "pkg/alpha.py": (
            "def score_alpha(records, weight):\n"
            "    total = 0\n"
            "    count = 0\n"
            "    for rec in records:\n"
            "        if rec.get('active'):\n"
            "            total += rec.get('value', 0) * weight\n"
            "            count += 1\n"
            "    if count == 0:\n"
            "        return 0.0\n"
            "    return round(total / count, 4)\n"
        ),
        "pkg/beta.py": (
            "def score_beta(entries, factor):\n"
            "    acc = 0\n"
            "    seen = 0\n"
            "    for item in entries:\n"
            "        if item.get('enabled'):\n"
            "            acc += item.get('amount', 0) * factor\n"
            "            seen += 1\n"
            "    if seen == 0:\n"
            "        return 0.0\n"
            "    return round(acc / seen, 4)\n"
        ),
    }
    snapshot = ProjectSnapshot.from_files(files, name="variants")

    over_findings = {f.rule: f for f in detect_over_engineering(snapshot)}
    assert "unimplemented-abstraction" in over_findings
    assert over_findings["unimplemented-abstraction"].symbol == "UnusedPort"
    assert "pass-through-layer" in over_findings
    assert over_findings["pass-through-layer"].symbol == "HollowFacade"
    assert "class-as-function" in over_findings
    assert over_findings["class-as-function"].symbol == "StatelessHelper"

    tok_a = normalize_code_tokens(files["pkg/alpha.py"])
    tok_b = normalize_code_tokens(files["pkg/beta.py"])
    assert token_similarity(tok_a, tok_b) == 1.0

    dups = detect_duplicate_functions(snapshot, QualityThresholds(duplicate_min_tokens=20))
    assert len(dups) == 1
    assert dups[0].symbol == "score_alpha"
    assert dups[0].related_locations == ["pkg/beta.py:1"]


def test_readability_performance_sql_structure_and_branches() -> None:
    files = {
        "src/foo.py": (
            "def foo(a, b, c, d, e, f, g):\n"
            "    for x in a:\n"
            "        with open('audit.log') as fp:\n"
            "            _ = fp.read()\n"
            "        for y in b:\n"
            "            for z in c:\n"
            "                if x and y:\n"
            "                    if z:\n"
            "                        return x\n"
            "    return None\n"
        ),
        "src/utils.py": "\n".join(f"def helper_{i}(x):\n    return x + {i}\n" for i in range(6)),
        "db/models.sql": (
            "CREATE TABLE articles (\n"
            "    id INTEGER PRIMARY KEY,\n"
            "    tag_ids TEXT\n"
            ");\n"
        ),
    }
    all_paths = [
        *files.keys(),
        "backup_old/legacy.py",
        "a/b/c/d/e/f/g/deep_module.py",
    ]
    snapshot = ProjectSnapshot.from_files(files, name="smells", all_paths=all_paths)

    thresholds = QualityThresholds(
        max_parameters=6,
        max_nesting=4,
        max_dir_depth=5,
        catch_all_module_symbols=4,
    )

    readability_rules = {f.rule for f in detect_readability_issues(snapshot, thresholds)}
    assert {"too-many-parameters", "deep-nesting", "vague-name"} <= readability_rules

    perf_rules = {f.rule for f in detect_performance_smells(snapshot)}
    assert {"io-in-loop", "nested-loops"} <= perf_rules

    sql_rules = {f.rule for f in detect_data_modeling_issues(snapshot)}
    assert "list-in-column" in sql_rules

    struct_rules = {f.rule for f in detect_structure_issues(snapshot, thresholds)}
    assert {"leftover-directory-name", "deep-directory", "catch-all-module"} <= struct_rules

    branch_findings = detect_branch_issues(
        branches=[
            BranchInfo(name="main", is_default=True),
            BranchInfo(name="random_branch_name", age_days=45.0),
            BranchInfo(name="feat/abandoned-work", last_commit_age_days=60.0),
        ],
        thresholds=QualityThresholds(long_lived_branch_days=30),
        direct_commits_on_default=["abc1234 hotfix straight on main"],
    )
    branch_rules = {f.rule: f for f in branch_findings}
    assert branch_rules["direct-commit-on-default-branch"].severity == QualitySeverity.P1
    assert branch_rules["long-lived-branch"].severity == QualitySeverity.P2
    assert branch_rules["stale-branch"].severity == QualitySeverity.P3
    assert branch_rules["branch-name-convention"].severity == QualitySeverity.P3


def test_control_plane_target_gate_and_audit_log() -> None:
    sample_dir = _quality_sample_dir()
    audit_log = AppendOnlyAuditLog()
    reviewer = QualityReviewer(audit_log=audit_log)

    # 1. Unauthorized target is rejected and recorded in the audit log
    with pytest.raises(TargetNotAuthorizedError):
        reviewer.review(sample_dir, collect_branches=False)

    events_after_denial = [e.event_type for e in audit_log.query()]
    assert "target.authorization.denied" in events_after_denial

    # 2. Pre-authorizing the target permits review and logs completion
    reviewer.authorize_target(sample_dir, authorized_by="sec-ops")
    report = reviewer.review(sample_dir, collect_branches=False)
    assert len(report.findings) >= 10

    event_types = [e.event_type for e in audit_log.query()]
    assert "target.marked_owned" in event_types
    assert "target.authorization.granted" in event_types
    assert "quality.review.completed" in event_types
    is_valid, _ = audit_log.verify_integrity()
    assert is_valid is True


def test_quality_review_pipeline_and_alias() -> None:
    tmpl = get_pipeline_template("quality-review")
    alias_tmpl = get_pipeline_template("revisao-de-qualidade")
    assert tmpl.name == "quality-review"
    assert alias_tmpl.name == "quality-review"
    assert "project_path" in tmpl.required_inputs

    sample_dir = _quality_sample_dir()
    fake_llm = FakeChatModel(
        responses=[
            "Step 1: split build_sales_report and batch customer lookup. Step 2: consolidate calculate_order_total.",
        ]
    )

    # 1. Refused when target is not authorized
    pipeline_unauth = build_pipeline("quality-review", model=fake_llm)
    res_unauth = pipeline_unauth.run(inputs={"project_path": str(sample_dir)}, dry_run=True)
    assert res_unauth.status == "failed"
    assert any("not marked as owned or authorized" in err for err in res_unauth.errors)

    # 2. Succeeds when target is owned
    audit_log = AppendOnlyAuditLog()
    pipeline = build_pipeline("revisao-de-qualidade", model=fake_llm, audit_log=audit_log)
    res = pipeline.run(
        inputs={
            "project_path": str(sample_dir),
            "owned_target": True,
            "authorized_by": "architect",
        },
        dry_run=True,
    )
    assert res.status == "completed"
    assert res.approval is not None
    assert res.approval.status == ApprovalStatus.DRY_RUN
    assert "quality_report" in res.data
    assert "quality_findings" in res.data
    assert "quality_remediation_plan" in res.data
    assert res.data["quality_severity_counts"]["P1"] >= 1
    assert any(e.event_type == "quality.review.completed" for e in audit_log.query())


def test_quality_skills_agent_and_cli(tmp_path: Path, capsys) -> None:
    skills = SkillCatalog.default()
    for slug in ("code-quality-review", "database-modeling"):
        skill = skills.get(slug)
        assert skill is not None, f"Missing skill '{slug}'"
        assert skill.description
        assert skill.content

    agents = AgentCatalog.default()
    reviewer_agent = agents.get_or_raise("code-quality-reviewer")
    assert reviewer_agent.sector == "qa"
    assert "code-quality-review" in reviewer_agent.skills
    assert "database-modeling" in reviewer_agent.skills

    # CLI refuses without --owned-target
    code_denied = main(["quality-review", str(_quality_sample_dir())])
    assert code_denied == 1
    _ = capsys.readouterr()

    # CLI writes Markdown report when --owned-target is passed
    out_file = tmp_path / "quality_report.md"
    code_ok = main(
        [
            "quality-review",
            str(_quality_sample_dir()),
            "--owned-target",
            "--authorized-by",
            "cli-tester",
            "--output",
            str(out_file),
        ]
    )
    assert code_ok == 0
    assert out_file.is_file()
    text = out_file.read_text(encoding="utf-8")
    assert "# Code Quality Review: quality_sample" in text
    assert "duplicate-function" in text
    assert "pass-through-wrapper" in text
    assert "single-implementation-abstraction" in text
    assert "long-function" in text
    _ = capsys.readouterr()
