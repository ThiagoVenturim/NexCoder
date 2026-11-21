"""Offline tests for Open-Source Contribution Mode (Issue #75):
- Read-only analysis (never executes third-party code or tests)
- RAG (`CodeSearchIndex`) and GraphRAG (`CodeGraph`, `CommunityDetector`) via `nexcoder-code-intel`
- Security & dependency vulnerability scanning via `nexcoder-security`
- Multi-language static bug, broken test, performance, and readability detection
- Prioritized fix proposals with code snippets and rationale
- Coordinated vulnerability disclosure (private channel routing, zero exploit payloads)
- 4-stage pipeline orchestration (`map_project` -> `find_problems` -> `propose_fixes` -> `build_report`)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.cli import main
from nexcoder_agents.engine.models import ApprovalStatus
from nexcoder_agents.engine.pipelines import build_pipeline, get_pipeline_template
from nexcoder_agents.oss_contribution import (
    DisclosureChannelType,
    OSSContributionAdvisor,
    OSSFindingCategory,
    sanitize_no_exploit,
)
from nexcoder_core.llm.fake import FakeChatModel


def _create_synthetic_oss_repo(base_dir: Path) -> tuple[Path, Path]:
    """Create a synthetic multi-language OSS repository with planted bugs, smells,
    a vulnerable dependency, and a canary side-effect that must never execute.
    """
    repo = base_dir / "synthetic_oss_lib"
    repo.mkdir(parents=True, exist_ok=True)
    canary_file = base_dir / "EXECUTED_CANARY.txt"

    (repo / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n",
        encoding="utf-8",
    )
    (repo / "CONTRIBUTING.md").write_text(
        "# Contributing to synthetic_oss_lib\n\n"
        "- Use Conventional Commits for all pull request titles.\n"
        "- Include unit tests for any bug fix.\n"
        "- Keep pull requests focused and minimal.\n",
        encoding="utf-8",
    )
    (repo / "SECURITY.md").write_text(
        "# Security Policy\n\n"
        "Please report vulnerabilities privately to security@synthetic-oss.example.org "
        "or via https://github.com/ThiagoVenturim/nexcoder/security/advisories/new.\n"
        "Never open a public issue with an exploit.\n",
        encoding="utf-8",
    )
    (repo / "requirements.txt").write_text(
        "jinja2==3.1.2\n",
        encoding="utf-8",
    )

    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "metrics.py").write_text(
        f"""\"\"\"Synthetic metrics module with planted bugs and code smells.\"\"\"

import subprocess

# Canary: if this file were ever imported or executed, it would create EXECUTED_CANARY.txt
if __name__ != "__never_run__":
    from pathlib import Path as _P
    _P(r"{canary_file}").write_text("EXECUTED", encoding="utf-8")


def append_metric(value: float, bucket: list[float] = []) -> list[float]:
    \"\"\"Planted bug 1: mutable default argument.\"\"\"
    bucket.append(value)
    return bucket


def compute_average(items: list[float]) -> float:
    \"\"\"Planted bug 2: unguarded division by zero when items is empty.\"\"\"
    return sum(items) / len(items)


def format_csv_report(rows: list[str]) -> str:
    \"\"\"Planted performance smell: string += concatenation in a loop.\"\"\"
    csv_text = ""
    for row in rows:
        csv_text += str(row) + "\\n"
    return csv_text


def run_diagnostic_shell(cmd: str) -> None:
    \"\"\"Planted security issue: subprocess with shell=True.\"\"\"
    try:
        subprocess.run(cmd, shell=True, check=False)
    except Exception:
        pass


def complex_pipeline_router(a: int, b: int, c: int, d: int, e: int, f: int, g: int) -> int:
    \"\"\"Planted readability smell: 7 parameters and deep branching.\"\"\"
    total = 0
    if a > 0:
        if b > 0:
            for item in range(c):
                if item % 2 == 0:
                    total += d
                elif e > 0:
                    total += f
    while g > 100:
        g -= 1
    return total
""",
        encoding="utf-8",
    )

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_metrics.py").write_text(
        f"""\"\"\"Synthetic test file with statically broken tests.\"\"\"

from pathlib import Path
from src.metrics import compute_average

# Canary inside test module: must never be executed by OSS analyzer!
Path(r"{canary_file}").write_text("TEST_EXECUTED", encoding="utf-8")


def test_compute_average_wrong_arity() -> None:
    # Planted broken test 1: compute_average takes 1 arg (items), but 3 are passed
    result = compute_average(10.0, 20.0, 30.0)
    assert result == 20.0


def test_empty_placeholder() -> None:
    # Planted broken test 2: test has no assertions
    _ = 1 + 1
""",
        encoding="utf-8",
    )

    web_dir = repo / "web"
    web_dir.mkdir()
    (web_dir / "widget.ts").write_text(
        """export function renderBadge(el: HTMLElement, status: string, label: string): void {
    console.log("Rendering badge", status);
    if (status == "active") {
        el.innerHTML = label;
    }
}
""",
        encoding="utf-8",
    )

    go_dir = repo / "pkg"
    go_dir.mkdir()
    (go_dir / "worker.go").write_text(
        """package worker

func RunJob(payload string) {
    _ = validatePayload(payload)
}
""",
        encoding="utf-8",
    )

    return repo, canary_file


def test_oss_skills_registered_in_catalog() -> None:
    skills = SkillCatalog.default()
    for slug in ("oss-contribution", "coordinated-disclosure"):
        skill = skills.get(slug)
        assert skill is not None, f"Expected skill '{slug}' in default catalog"
        assert skill.description
        assert skill.content

    agents = AgentCatalog.default()
    architect = agents.get_or_raise("lead-architect")
    assert "oss-contribution" in architect.skills

    auditor = agents.get_or_raise("security-auditor")
    assert "coordinated-disclosure" in auditor.skills
    assert "oss-contribution" in auditor.skills


def test_read_only_enforcement_rejects_non_read_only(tmp_path: Path) -> None:
    repo, _ = _create_synthetic_oss_repo(tmp_path)
    advisor = OSSContributionAdvisor()
    with pytest.raises(ValueError, match="strictly read-only"):
        advisor.analyze_oss_project(repo, read_only=False)


def test_offline_analysis_on_synthetic_repo_finds_planted_bugs_without_executing_code(
    tmp_path: Path,
) -> None:
    repo, canary_file = _create_synthetic_oss_repo(tmp_path)
    advisor = OSSContributionAdvisor()

    report = advisor.analyze_oss_project(
        "https://github.com/ThiagoVenturim/nexcoder",
        local_checkout=repo,
        read_only=True,
        allow_public_security_issue=True,  # Intentionally test that guardrail blocks public security issue!
        dry_run=True,
    )

    # 1. CRITICAL: Verify third-party code and tests were NEVER executed
    assert not canary_file.exists(), "Third-party code or tests must NEVER be executed!"
    assert report.project_map.read_only_verified is True

    # 2. Verify code-intel RAG & GraphRAG mapping across languages
    pm = report.project_map
    assert pm.project_name == "synthetic_oss_lib"
    assert pm.files_indexed >= 4
    assert pm.symbols_extracted >= 5
    assert pm.graph_nodes >= 5
    assert pm.communities_detected >= 1
    assert {"python", "typescript", "go"} <= set(pm.languages_breakdown.keys())
    assert pm.governance.has_contributing_md is True
    assert pm.governance.has_security_md is True
    assert pm.governance.license_type == "MIT"
    assert pm.governance.preferred_disclosure_channel == DisclosureChannelType.SECURITY_MD_URL

    # 3. Verify all 4 categories of findings (security, bug, performance, readability)
    categories_found = {f.category for f in report.findings}
    assert OSSFindingCategory.SECURITY in categories_found
    assert OSSFindingCategory.BUG in categories_found
    assert OSSFindingCategory.PERFORMANCE in categories_found
    assert OSSFindingCategory.READABILITY in categories_found

    titles = [f.title for f in report.findings]
    # Planted Python bugs
    assert any("Mutable default argument in `append_metric`" in t for t in titles)
    assert any("Unguarded division by zero risk in `compute_average`" in t for t in titles)
    assert any("Swallowed exception in `run_diagnostic_shell`" in t for t in titles)
    # Planted broken tests (detected statically without running pytest!)
    assert any("Broken test `test_compute_average_wrong_arity`" in t for t in titles)
    assert any("Broken test `test_empty_placeholder`" in t for t in titles)
    # Planted multi-language bugs & smells
    assert any("Loose equality operator" in t for t in titles)
    assert any("Ignored error return in Go" in t for t in titles)
    # Planted performance & readability improvements
    assert any("Repeated string concatenation inside loop" in t for t in titles)
    assert any("High complexity or parameter count" in t for t in titles)
    # Planted security & dependency issues via nexcoder-security
    assert any("jinja2" in t.lower() or "shell=true" in t.lower() or "innerhtml" in t.lower() for t in titles)

    # 4. Verify prioritization order (security & bug before performance & readability)
    ranks = [f.priority_rank for f in report.findings]
    assert ranks == list(range(1, len(report.findings) + 1))
    assert report.findings[0].category == OSSFindingCategory.SECURITY
    assert report.findings[-1].category == OSSFindingCategory.READABILITY

    # 5. Verify fix proposals and zero exploit payloads
    assert len(report.suggestions) == len(report.findings)
    for sug in report.suggestions:
        assert sug.original_snippet
        assert sug.suggested_snippet
        assert sug.rationale
        assert sug.contains_exploit_payload is False

    # 6. Verify Coordinated Vulnerability Disclosure guardrail
    sec_actions = [a for a in report.upstream_actions if a.action_type == "private_security_report"]
    pub_actions = [a for a in report.upstream_actions if a.action_type == "public_pull_request"]
    assert len(sec_actions) >= 2
    assert len(pub_actions) >= 4
    for sa in sec_actions:
        assert sa.blocked_public_disclosure is True
        assert "security/advisories" in sa.channel
        assert sa.submitted is False
        assert "No exploit payload included" in sa.body_preview

    # 7. Verify Markdown report generation
    md = report.to_markdown()
    assert "# Open-Source Contribution Report: synthetic_oss_lib" in md
    assert "## 1. Project Map & Code Intelligence (RAG / GraphRAG)" in md
    assert "## 2. Project Governance & Coordinated Vulnerability Disclosure" in md
    assert "## 3. Prioritized Findings (Bug, Security, Performance, Readability)" in md
    assert "## 4. Proposed Fixes & Technical Justifications" in md
    assert "## 5. Upstream Contribution & Responsible Disclosure Plan" in md


def test_sanitize_no_exploit_strips_offensive_payloads() -> None:
    dirty = "Demonstration: <script>alert(1)</script> or DROP TABLE users; rm -rf /"
    cleaned, detected = sanitize_no_exploit(dirty)
    assert detected is True
    assert "<script>" not in cleaned
    assert "DROP TABLE" not in cleaned
    assert "rm -rf" not in cleaned
    assert "[REDACTED_OFFENSIVE_PAYLOAD]" in cleaned


def test_oss_contribution_pipeline_orchestration(tmp_path: Path) -> None:
    repo, canary_file = _create_synthetic_oss_repo(tmp_path)
    tmpl = get_pipeline_template("oss-contribution")
    assert tmpl.category == "open-source"
    assert "repo_path_or_url" in tmpl.required_inputs

    fake_llm = FakeChatModel(
        responses=[
            "Approved: findings are accurate, diffs are minimal, and security advisories use private channel."
        ]
    )
    pipeline = build_pipeline("oss-contribution", model=fake_llm)
    res = pipeline.run(
        inputs={
            "repo_path_or_url": str(repo),
            "allow_public_security_issue": False,
        },
        dry_run=True,
    )

    assert not canary_file.exists()
    assert res.status == "completed"
    assert res.approval is not None
    assert res.approval.status == ApprovalStatus.DRY_RUN
    assert "oss_project_map" in res.data
    assert "oss_findings" in res.data
    assert "oss_suggestions" in res.data
    assert "oss_upstream_actions" in res.data
    assert "oss_report_markdown" in res.data
    assert len(res.data["oss_findings"]) >= 6


def test_cli_analyze_oss_command(tmp_path: Path, capsys) -> None:
    repo, canary_file = _create_synthetic_oss_repo(tmp_path)
    out_file = tmp_path / "oss_report.md"

    code = main(
        [
            "analyze-oss",
            str(repo),
            "--output",
            str(out_file),
        ]
    )
    assert code == 0
    assert not canary_file.exists()
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Open-Source Contribution Report: synthetic_oss_lib" in content

    # Missing directory returns 1
    code_err = main(["analyze-oss", str(tmp_path / "non_existent_oss_repo")])
    assert code_err == 1
    _ = capsys.readouterr()
