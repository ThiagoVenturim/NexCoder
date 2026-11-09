"""End-to-end offline quickstart pipeline for nexcoder.

Demonstrates the software delivery lifecycle from raw idea to security gate:
1. Idea intake and architectural jury committee (nexcoder-ideation)
2. Product Requirement Document (PRD) generation
3. Sprint planning and task decomposition in a local Git repository (nexcoder-planning)
4. Code intelligence indexing and code RAG over sample_project (nexcoder-code-intel)
5. Multi-agent delivery pipeline execution (nexcoder-agents)
6. Security gate evaluation and vulnerability scan (nexcoder-security)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nexcoder_agents.engine.pipelines import build_pipeline
from nexcoder_code_intel.retrieval import CodeSearchIndex
from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_ideation.output.prd import PRDGenerator
from nexcoder_ideation.pipeline import IdeationPipeline
from nexcoder_ideation.search.providers import MockSearchProvider
from nexcoder_planning.capacity import (
    CapacityCalculator,
    SprintCapacityConfig,
    TeamMember,
)
from nexcoder_planning.models import (
    AcceptanceCriterion,
    Epic,
    Plan,
    Story,
    Task,
)
from nexcoder_security.gate import SecurityGateEvaluator
from nexcoder_security.scanners import MultiScannerEngine


def run_quickstart(output_dir: Path | str | None = None) -> dict[str, Any]:
    """Execute all quickstart lifecycle stages offline and return artifact paths."""
    base_dir = Path(__file__).parent.resolve()
    sample_project_dir = base_dir / "sample_project"

    if output_dir:
        out_dir = Path(output_dir).resolve()
    else:
        out_dir = base_dir / ".quickstart_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Path] = {}

    print("======================================================================")
    print("nexcoder Offline Quickstart: End-to-End Delivery Pipeline")
    print("======================================================================\n")

    # -------------------------------------------------------------------------
    # Stage 1: Ideation Intake & Architectural Jury
    # -------------------------------------------------------------------------
    print("[1/6] Ideation & Architectural Jury")
    print("----------------------------------------------------------------------")
    fake_ideation_model = FakeChatModel(
        responses=[
            "Structured proposal for task deadline management.",
            "Market analysis complete: strong developer demand for scheduling.",
            "Jury consensus: GO. High architectural feasibility.",
        ]
    )
    ideation_pipeline = IdeationPipeline(
        search_provider=MockSearchProvider(),
        model=fake_ideation_model,
        allow_network=False,
    )
    raw_idea_text = (
        "Add due dates and deadline tracking to task management library: "
        "allow users to specify ISO deadlines, compute overdue status, and filter pending tasks."
    )
    ideation_output, _secret = ideation_pipeline.run(raw_idea_text, dry_run=False)
    verdict = ideation_output.jury_verdict

    verdict_file = out_dir / "jury_verdict.json"
    verdict_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
    artifacts["jury_verdict"] = verdict_file

    print(f"Idea Title:    {ideation_output.structured_idea.title}")
    print(f"Jury Decision: {verdict.verdict.value.upper()} (Consensus: {verdict.consensus_reached})")
    print(
        f"Votes:         {verdict.go_votes} GO / {verdict.pivot_votes} PIVOT / "
        f"{verdict.no_go_votes} NO-GO (Total jurors: {verdict.total_jurors})"
    )
    print(f"Artifact:      {verdict_file}\n")

    # -------------------------------------------------------------------------
    # Stage 2: PRD Generation
    # -------------------------------------------------------------------------
    print("[2/6] PRD Generation")
    print("----------------------------------------------------------------------")
    prd_text = PRDGenerator.generate(
        idea=ideation_output.structured_idea,
        report=ideation_output.research_report,
        verdict=ideation_output.jury_verdict,
        architecture=ideation_output.architecture,
        gate=ideation_output.approval_gate,
    )
    prd_file = out_dir / "prd.md"
    prd_file.write_text(prd_text, encoding="utf-8")
    artifacts["prd"] = prd_file

    print("PRD generated successfully from vetted architecture and jury rubric.")
    print(f"Total lines:   {len(prd_text.splitlines())}")
    print(f"Artifact:      {prd_file}\n")

    # -------------------------------------------------------------------------
    # Stage 3: Planning & Sprint Decomposition (Local Git Repository)
    # -------------------------------------------------------------------------
    print("[3/6] Planning & Sprint Decomposition (Git Repository)")
    print("----------------------------------------------------------------------")
    planning_repo_dir = out_dir / "planning_repo"
    planning_repo_dir.mkdir(parents=True, exist_ok=True)

    plan = Plan(
        title="Task Due Dates and Overdue Tracking",
        epics=[
            Epic(
                id="EP-01",
                title="Due Date Scheduling",
                stories=[
                    Story(
                        id="US-01",
                        title="Task Due Date Support",
                        tasks=[
                            Task(
                                id="TSK-01",
                                title="Add due_date field to Task model",
                                layer="core",
                                estimate_hours=3.0,
                                recommended_agent="backend-engineer",
                                acceptance_criteria=[
                                    AcceptanceCriterion(
                                        given="A task definition",
                                        when="A due date is provided",
                                        then="Store ISO formatted date string",
                                    )
                                ],
                            ),
                            Task(
                                id="TSK-02",
                                title="Implement is_overdue comparison logic",
                                layer="core",
                                estimate_hours=4.0,
                                dependencies=["TSK-01"],
                                recommended_agent="backend-engineer",
                                acceptance_criteria=[
                                    AcceptanceCriterion(
                                        given="A task with due date in the past",
                                        when="Compared against reference date",
                                        then="Return True indicating overdue",
                                    )
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    )

    calculator = CapacityCalculator()
    team = [TeamMember(name="lead-dev", daily_hours=6.0, working_days=5)]
    config = SprintCapacityConfig(sprint_name="Sprint-1", team=team)
    sprint_plan = calculator.plan_sprint(plan, config)

    sprint_json = planning_repo_dir / "sprint_1.json"
    sprint_json.write_text(sprint_plan.model_dump_json(indent=2), encoding="utf-8")
    artifacts["sprint_plan"] = sprint_json

    tasks_md = planning_repo_dir / "BACKLOG.md"
    tasks_md.write_text(
        f"# Sprint Backlog: {sprint_plan.sprint_name}\n\n"
        f"Scheduled: {len(sprint_plan.scheduled_tasks)} tasks "
        f"({sprint_plan.capacity_report.planned_hours} hours planned / "
        f"{sprint_plan.capacity_report.effective_capacity_hours} hours capacity)\n\n"
        + "\n".join(f"- [{t.id}] {t.title} ({t.estimate_hours}h)" for t in sprint_plan.scheduled_tasks),
        encoding="utf-8",
    )
    artifacts["backlog"] = tasks_md

    # Initialize git repo in planning folder if not already initialized
    git_bin = shutil.which("git") or "git"
    if not (planning_repo_dir / ".git").exists():
        subprocess.run([git_bin, "init"], cwd=planning_repo_dir, check=True, capture_output=True)  # noqa: S603
    subprocess.run([git_bin, "add", "."], cwd=planning_repo_dir, check=True, capture_output=True)  # noqa: S603
    subprocess.run(
        [
            git_bin,
            "-c",
            "user.name=nexcoder",
            "-c",
            "user.email=nexcoder@local",
            "commit",
            "-m",
            "chore: initialize sprint backlog",
        ],
        cwd=planning_repo_dir,
        check=True,
        capture_output=True,
    )  # noqa: S603

    print(f"Scheduled Sprint: {sprint_plan.sprint_name}")
    print(f"Planned Hours:    {sprint_plan.capacity_report.planned_hours}h")
    print(f"Scheduled Tasks:  {len(sprint_plan.scheduled_tasks)}")
    print(f"Git Repository:   {planning_repo_dir}\n")

    # -------------------------------------------------------------------------
    # Stage 4: Code Intelligence & AST Code Search
    # -------------------------------------------------------------------------
    print("[4/6] Code Intelligence Indexing & AST Code Search")
    print("----------------------------------------------------------------------")
    index_db_file = out_dir / "code_intel.db"
    with CodeSearchIndex(db_path=index_db_file) as search_index:
        indexed_count = search_index.index_directory(sample_project_dir)
        search_results = search_index.search("is_overdue due_date", top_k=2)

    artifacts["code_intel_db"] = index_db_file

    rag_question = "How is overdue status evaluated in sample_project?"
    rag_snippet = search_results[0].get("text", "") if search_results else "No snippet found"
    rag_file = out_dir / "rag_summary.txt"
    rag_file.write_text(
        f"Question: {rag_question}\n\nTop Retrieved Code Chunk:\n{rag_snippet}\n",
        encoding="utf-8",
    )
    artifacts["rag_summary"] = rag_file

    print(f"Source Files:     {indexed_count} files indexed from sample_project")
    print(f"RAG Question:     {rag_question}")
    print(f"Retrieved Chunks: {len(search_results)}")
    print(f"Artifact:         {rag_file}\n")

    # -------------------------------------------------------------------------
    # Stage 5: Multi-Agent Delivery Pipeline
    # -------------------------------------------------------------------------
    print("[5/6] Multi-Agent Delivery Pipeline")
    print("----------------------------------------------------------------------")
    agent_model = FakeChatModel(
        responses=[
            "Root cause detected: inverted comparison in TaskService.is_overdue.",
            "Synthesized patch: reference_date > task.due_date.",
        ]
    )
    pipeline = build_pipeline("bugfix-delivery", model=agent_model)
    pipeline_result = pipeline.run(
        inputs={
            "issue_id": "TSK-02",
            "description": "Fix overdue date comparison logic in TaskService",
            "error_stack": "AssertionError: is_overdue returned False for past date",
        },
        dry_run=True,
    )

    pipeline_result_file = out_dir / "pipeline_run.json"
    pipeline_result_file.write_text(pipeline_result.model_dump_json(indent=2), encoding="utf-8")
    artifacts["pipeline_result"] = pipeline_result_file

    print("Pipeline:         bugfix-delivery")
    print(f"Execution Status: {pipeline_result.status} (dry_run mode)")
    print(f"Execution Steps:  {len(pipeline_result.history)}")
    print(f"Artifact:         {pipeline_result_file}\n")

    # -------------------------------------------------------------------------
    # Stage 6: Security Release Gate
    # -------------------------------------------------------------------------
    print("[6/6] Security Release Gate Evaluation")
    print("----------------------------------------------------------------------")
    scanner_engine = MultiScannerEngine()
    scan_result = scanner_engine.scan(
        sample_project_dir,
        enabled_scanners=["semgrep", "bandit"],
        force_offline=True,
    )

    evaluator = SecurityGateEvaluator()
    gate_verdict = evaluator.evaluate(scan_result)

    security_file = out_dir / "security_gate_verdict.json"
    security_file.write_text(gate_verdict.model_dump_json(indent=2), encoding="utf-8")
    artifacts["security_verdict"] = security_file

    status_label = "PASSED" if gate_verdict.passed else "BLOCKED"
    print(f"Target Scanned:   {sample_project_dir.name}")
    print(f"Findings Count:   {len(scan_result.findings)}")
    print(f"Gate Verdict:     {status_label}")
    print(f"Summary:          {gate_verdict.summary}")
    print(f"Artifact:         {security_file}\n")

    # -------------------------------------------------------------------------
    # Completion Summary
    # -------------------------------------------------------------------------
    print("======================================================================")
    print("Quickstart Completed Successfully")
    print("======================================================================")
    print(f"Generated artifacts located at:\n  {out_dir}\n")
    for name, path in artifacts.items():
        print(f"  - {name}: {path.name}")
    print("======================================================================\n")

    return {
        "status": "success",
        "artifacts_dir": out_dir,
        "artifacts": artifacts,
        "jury_verdict": verdict,
        "sprint_plan": sprint_plan,
        "gate_verdict": gate_verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run nexcoder offline end-to-end quickstart.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom target directory for generated artifacts",
    )
    args = parser.parse_args()
    run_quickstart(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
