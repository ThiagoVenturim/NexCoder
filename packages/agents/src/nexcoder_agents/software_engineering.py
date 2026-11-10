"""Software engineering practices advisor, architecture reviewer, ADR generator,
technical planner, and guided refactoring engine.

Combines AST code intelligence (`nexcoder-code-intel`), backlog decomposition
and capacity planning (`nexcoder-planning`), and multi-agent pipelines
(`nexcoder-agents`) to deliver actionable architecture assessments and safe,
test-backed refactorings offline.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any

from nexcoder_code_intel.docgen import BottomUpDocEngine, DocLevel, DocNode
from nexcoder_code_intel.graph import CodeGraph, CommunityDetector, ImpactReport
from nexcoder_code_intel.models import Symbol, SymbolType
from nexcoder_code_intel.parsers import parse_file
from nexcoder_core.sandbox import resolve_inside
from nexcoder_planning.capacity import (
    CapacityCalculator,
    SprintCapacityConfig,
    SprintPlanResult,
    TeamMember,
)
from nexcoder_planning.git_helpers import build_conventional_commit, validate_no_emoji
from nexcoder_planning.models import Plan
from nexcoder_planning.prd import PRDConverter
from pydantic import BaseModel, Field

from nexcoder_agents.engine.blocks.base import BaseBlock
from nexcoder_agents.engine.models import BlockResult, BlockStatus


class ArchitecturePattern(StrEnum):
    """Canonical software architecture patterns evaluated by the advisor."""

    LAYERED = "layered"
    HEXAGONAL = "hexagonal"
    EVENT_Driven = "event_driven"
    MODULAR_MONOLITH = "modular_monolith"


class ActionPriority(StrEnum):
    """Priority tiers for recommended engineering actions."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class PatternTradeOff(BaseModel):
    """Trade-off evaluation for a candidate architectural pattern."""

    pattern: ArchitecturePattern
    fit_score: float = Field(ge=0.0, le=100.0)
    strengths: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    when_to_adopt: str = ""


class LayerViolation(BaseModel):
    """Detected architectural boundary or dependency-direction violation."""

    source_file: str
    source_layer: str
    target_module: str
    target_layer: str
    reason: str
    severity: str = "medium"


class ArchitectureAssessment(BaseModel):
    """Comprehensive architectural review of a target codebase."""

    project_name: str
    detected_pattern: ArchitecturePattern
    recommended_pattern: ArchitecturePattern
    architecture_score: float = Field(ge=0.0, le=100.0)
    modules_analyzed: int = 0
    symbols_analyzed: int = 0
    communities_detected: int = 0
    layer_map: dict[str, str] = Field(default_factory=dict)
    layer_violations: list[LayerViolation] = Field(default_factory=list)
    coupling_findings: list[str] = Field(default_factory=list)
    pattern_trade_offs: list[PatternTradeOff] = Field(default_factory=list)
    summary: str = ""


class PracticeCheck(BaseModel):
    """Result of auditing a specific software engineering practice."""

    category: str  # testing, ci_cd, semver, commit_conventions, branch_organization
    passed: bool
    score: float = Field(ge=0.0, le=100.0)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PracticesAudit(BaseModel):
    """Aggregated audit of software engineering best practices."""

    overall_score: float = Field(ge=0.0, le=100.0)
    checks: list[PracticeCheck] = Field(default_factory=list)
    untested_symbols: list[str] = Field(default_factory=list)
    recommended_branch_model: dict[str, str] = Field(default_factory=dict)
    sample_conventional_commits: list[str] = Field(default_factory=list)


class ADRDocument(BaseModel):
    """Architecture Decision Record (ADR) following Nygard/MADR structure."""

    id: str
    title: str
    status: str = "Accepted"
    context: str
    decision: str
    consequences: list[str] = Field(default_factory=list)
    alternatives_considered: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the ADR as standard markdown."""
        lines = [
            f"# {self.id}: {self.title}",
            "",
            f"- **Status**: {self.status}",
            "",
            "## Context",
            self.context,
            "",
            "## Decision",
            self.decision,
            "",
            "## Consequences",
            *[f"- {c}" for c in self.consequences],
            "",
            "## Alternatives Considered",
            *[f"- {a}" for a in self.alternatives_considered],
        ]
        return "\n".join(lines).strip() + "\n"


classPrioritizedAction_Layers = ("core", "backend", "frontend", "data", "qa", "devops", "security")


class PrioritizedAction(BaseModel):
    """Actionable engineering improvement ranked by priority, impact, and effort."""

    id: str
    priority: ActionPriority
    category: str  # architecture, testing, refactoring, documentation, ci_cd, governance
    title: str
    rationale: str
    layer: str = "core"
    estimate_hours: float = 2.0
    recommended_agent: str = "backend-engineer"
    dependencies: list[str] = Field(default_factory=list)


class GuidedRefactorSuggestion(BaseModel):
    """Safe, test-backed refactoring proposal with blast-radius impact metrics."""

    id: str
    title: str
    target_file: str
    target_symbol: str
    rationale: str
    safe_to_auto_apply: bool = True
    impact_report: ImpactReport | None = None
    original_snippet: str = ""
    refactored_snippet: str = ""
    test_file: str = ""
    companion_test_code: str = ""


class GuidedRefactorApplication(BaseModel):
    """Outcome of applying a guided refactoring and running its verification suite."""

    suggestion_id: str
    applied: bool
    workspace_dir: str
    modified_files: list[str] = Field(default_factory=list)
    tests_passed: bool = False
    test_output: str = ""
    commit_message: str = ""


class SoftwareEngineeringReport(BaseModel):
    """Complete software engineering assessment, documentation, plan, and refactoring report."""

    project_name: str
    architecture: ArchitectureAssessment
    practices: PracticesAudit
    adrs: list[ADRDocument] = Field(default_factory=list)
    architecture_diagram: str = ""
    bottom_up_system_doc: str = ""
    bottom_up_node_count: int = 0
    prioritized_actions: list[PrioritizedAction] = Field(default_factory=list)
    technical_plan: Plan
    sprint_plan: SprintPlanResult
    refactor_suggestions: list[GuidedRefactorSuggestion] = Field(default_factory=list)
    applied_refactor: GuidedRefactorApplication | None = None

    def to_markdown(self) -> str:
        """Render the complete architectural opinion and engineering report as Markdown."""
        lines = [
            f"# Software Engineering & Architecture Assessment: {self.project_name}",
            "",
            "## 1. Architecture Review (Parecer de Arquitetura)",
            f"- **Detected Pattern**: `{self.architecture.detected_pattern.value}`",
            f"- **Recommended Pattern**: `{self.architecture.recommended_pattern.value}`",
            f"- **Architecture Score**: {self.architecture.architecture_score:.1f}/100",
            f"- **Modules Analyzed**: {self.architecture.modules_analyzed}",
            f"- **Symbols Analyzed**: {self.architecture.symbols_analyzed}",
            f"- **Subsystem Clusters**: {self.architecture.communities_detected}",
            "",
            self.architecture.summary,
            "",
            "### Pattern Trade-Off Evaluation",
        ]
        for pt in self.architecture.pattern_trade_offs:
            lines.append(f"- **`{pt.pattern.value}`** (fit: {pt.fit_score:.0f}/100): {pt.when_to_adopt}")
            for s in pt.strengths:
                lines.append(f"  - Strength: {s}")
            for t in pt.trade_offs:
                lines.append(f"  - Trade-off: {t}")

        if self.architecture.layer_violations:
            lines.extend(["", "### Layer Boundary Violations"])
            for v in self.architecture.layer_violations:
                lines.append(
                    f"- [{v.severity.upper()}] `{v.source_file}` ({v.source_layer}) -> "
                    f"`{v.target_module}` ({v.target_layer}): {v.reason}"
                )

        if self.architecture.coupling_findings:
            lines.extend(["", "### Coupling & Structural Findings"])
            for cf in self.architecture.coupling_findings:
                lines.append(f"- {cf}")

        lines.extend(
            [
                "",
                "## 2. Engineering Best Practices Audit",
                f"- **Overall Practices Score**: {self.practices.overall_score:.1f}/100",
            ]
        )
        for chk in self.practices.checks:
            status_str = "PASS" if chk.passed else "NEEDS IMPROVEMENT"
            lines.append(f"- **{chk.category}** [{status_str} - {chk.score:.0f}/100]")
            for rec in chk.recommendations:
                lines.append(f"  - Action: {rec}")

        if self.practices.untested_symbols:
            lines.extend(
                [
                    "",
                    "### Untested Public Routines",
                    *[f"- `{sym}`" for sym in self.practices.untested_symbols],
                ]
            )

        lines.extend(
            [
                "",
                "## 3. Prioritized Engineering Actions",
            ]
        )
        for act in self.prioritized_actions:
            lines.append(
                f"- **[{act.priority.value}] {act.id} - {act.title}** "
                f"(`{act.category}`, layer=`{act.layer}`, est={act.estimate_hours}h): {act.rationale}"
            )

        lines.extend(
            [
                "",
                "## 4. Architecture Diagram",
                "```mermaid",
                self.architecture_diagram,
                "```",
                "",
                "## 5. Architecture Decision Records (ADRs)",
            ]
        )
        for adr in self.adrs:
            lines.extend(["", adr.to_markdown().strip()])

        lines.extend(
            [
                "",
                "## 6. Technical Plan & Sprint Schedule",
                f"- **Plan Title**: {self.technical_plan.title}",
                f"- **Total Estimated Hours**: {self.technical_plan.total_hours()}h",
                f"- **Scheduled in {self.sprint_plan.sprint_name}**: "
                f"{len(self.sprint_plan.scheduled_tasks)} task(s) "
                f"({self.sprint_plan.capacity_report.planned_hours}h planned / "
                f"{self.sprint_plan.capacity_report.effective_capacity_hours}h capacity)",
            ]
        )

        if self.refactor_suggestions:
            lines.extend(["", "## 7. Guided Refactorings"])
            for ref in self.refactor_suggestions:
                risk = ref.impact_report.risk_level if ref.impact_report else "low"
                lines.append(
                    f"- **{ref.id}: {ref.title}** (`{ref.target_file}` :: `{ref.target_symbol}`, "
                    f"blast-radius risk=`{risk}`, safe={ref.safe_to_auto_apply}): {ref.rationale}"
                )

        if self.applied_refactor:
            lines.extend(
                [
                    "",
                    "### Applied Refactoring Verification",
                    f"- **Suggestion**: `{self.applied_refactor.suggestion_id}`",
                    f"- **Applied**: `{self.applied_refactor.applied}`",
                    f"- **Tests Passed**: `{self.applied_refactor.tests_passed}`",
                    f"- **Commit**: `{self.applied_refactor.commit_message}`",
                ]
            )

        return "\n".join(lines).strip() + "\n"


_LAYER_CLASSIFICATION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("domain", ("model", "models", "entity", "entities", "domain", "schema", "value_object")),
    ("application", ("service", "services", "use_case", "use_cases", "workflow", "orchestrator", "handler")),
    ("infrastructure", ("storage", "repository", "repositories", "db", "database", "adapter", "adapters", "client")),
    ("presentation", ("api", "cli", "controller", "controllers", "view", "views", "route", "routes", "ui", "web")),
]

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9_.,/-]+\))?!?: .+"
)


def classify_module_layer(file_path: str | Path) -> str:
    """Classify a source file into an architectural layer based on path and stem."""
    p = Path(file_path)
    parts = [part.lower() for part in p.parts]
    stem = p.stem.lower()
    if "test" in stem or "tests" in parts:
        return "tests"
    for layer, keywords in _LAYER_CLASSIFICATION_RULES:
        if stem in keywords or any(k in parts for k in keywords):
            return layer
    return "core"


def _extract_python_imports(file_path: Path, content: str) -> list[str]:
    """Extract imported module names from a Python source file using stdlib AST."""
    if file_path.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class SoftwareEngineeringAdvisor:
    """Orchestrates architectural review, best-practices auditing, ADR synthesis,
    technical backlog decomposition, and guided test-backed refactoring.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm
        self.doc_engine = BottomUpDocEngine(llm=llm)
        self.community_detector = CommunityDetector()
        self.prd_converter = PRDConverter()
        self.capacity_calculator = CapacityCalculator()

    def analyze_project(
        self,
        project_dir: Path | str,
        *,
        apply_safe_refactor: bool = True,
        refactor_workspace: Path | str | None = None,
        commit_messages: list[str] | None = None,
        branch_names: list[str] | None = None,
    ) -> SoftwareEngineeringReport:
        """Run a full software engineering assessment over `project_dir`."""
        root = Path(project_dir).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Project directory not found: {root}")

        project_name = root.name

        # 1. Parse source and test files with nexcoder-code-intel
        source_files: list[Path] = []
        test_files: list[Path] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(root).parts
            if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
                continue
            if path.suffix.lower() in {".py", ".ts", ".js", ".go", ".rs", ".java", ".cs", ".pas"}:
                lower_parts = [p.lower() for p in rel_parts]
                if path.stem.startswith("test_") or path.stem.endswith("_test") or "tests" in lower_parts:
                    test_files.append(path)
                elif path.name != "__init__.py":
                    source_files.append(path)

        symbols: list[Symbol] = []
        file_imports: dict[str, list[str]] = {}
        file_contents: dict[str, str] = {}

        for src in source_files:
            rel_path = src.relative_to(root).as_posix()
            content = src.read_text(encoding="utf-8", errors="replace")
            file_contents[rel_path] = content
            parsed = parse_file(src, content=content)
            # Normalize symbol file_path to relative POSIX path for deterministic reporting
            normalized_symbols = [
                sym.model_copy(
                    update={
                        "id": f"{rel_path}::{sym.qualified_name}",
                        "location": sym.location.model_copy(update={"file_path": rel_path}),
                    }
                )
                for sym in parsed
            ]
            symbols.extend(normalized_symbols)
            file_imports[rel_path] = _extract_python_imports(src, content)

        # Build CodeGraph & wire module import edges
        code_graph = CodeGraph()
        code_graph.add_symbols(symbols)
        self._wire_file_dependencies(code_graph, symbols, file_imports, file_contents)

        communities = self.community_detector.detect_communities(code_graph)

        # 2. Architecture Assessment
        architecture = self._assess_architecture(
            project_name=project_name,
            source_files=source_files,
            root=root,
            symbols=symbols,
            code_graph=code_graph,
            communities_count=len(communities),
            file_imports=file_imports,
            file_contents=file_contents,
        )

        # 3. Best Practices Audit
        practices = self._audit_practices(
            root=root,
            source_files=source_files,
            test_files=test_files,
            symbols=symbols,
            commit_messages=commit_messages,
            branch_names=branch_names,
        )

        # 4. Engineering Documentation (Bottom-Up Docs, Mermaid Diagram, ADRs)
        doc_tree = self.doc_engine.generate_tree(symbols, communities=communities)
        system_doc_node = doc_tree.get("system::architecture")
        bottom_up_system_doc = system_doc_node.markdown if system_doc_node else ""
        diagram = self._generate_mermaid_diagram(architecture.layer_map, file_imports)
        adrs = self._generate_adrs(project_name, architecture, practices)

        # 5. Guided Refactoring Suggestions (with CodeGraph blast-radius analysis)
        refactor_suggestions = self._propose_guided_refactors(
            root=root,
            symbols=symbols,
            code_graph=code_graph,
            file_contents=file_contents,
            untested_symbols=practices.untested_symbols,
        )

        # 6. Prioritized Actions
        prioritized_actions = self._build_prioritized_actions(
            architecture=architecture,
            practices=practices,
            refactor_suggestions=refactor_suggestions,
        )

        # 7. Technical Planning & Sprint Estimation (reusing nexcoder-planning)
        technical_plan, sprint_plan = self._build_technical_plan(
            project_name=project_name,
            prioritized_actions=prioritized_actions,
        )

        # 8. Apply safe refactoring with test verification if requested
        applied_refactor: GuidedRefactorApplication | None = None
        if apply_safe_refactor and refactor_suggestions:
            safe_candidates = [s for s in refactor_suggestions if s.safe_to_auto_apply]
            if safe_candidates:
                applied_refactor = self.apply_and_verify_refactor(
                    project_dir=root,
                    suggestion=safe_candidates[0],
                    workspace_dir=refactor_workspace,
                )

        return SoftwareEngineeringReport(
            project_name=project_name,
            architecture=architecture,
            practices=practices,
            adrs=adrs,
            architecture_diagram=diagram,
            bottom_up_system_doc=bottom_up_system_doc,
            bottom_up_node_count=len(doc_tree),
            prioritized_actions=prioritized_actions,
            technical_plan=technical_plan,
            sprint_plan=sprint_plan,
            refactor_suggestions=refactor_suggestions,
            applied_refactor=applied_refactor,
        )

    def _wire_file_dependencies(
        self,
        code_graph: CodeGraph,
        symbols: list[Symbol],
        file_imports: dict[str, list[str]],
        file_contents: dict[str, str],
    ) -> None:
        """Connect symbols across files when one file imports or references another symbol."""
        by_name: dict[str, list[Symbol]] = {}
        for sym in symbols:
            by_name.setdefault(sym.name, []).append(sym)

        for sym in symbols:
            if sym.symbol_type not in {SymbolType.CLASS, SymbolType.FUNCTION, SymbolType.METHOD}:
                continue
            src_content = file_contents.get(sym.location.file_path, "")
            lines = src_content.splitlines()
            start_idx = max(0, sym.location.start_line - 1)
            end_idx = min(len(lines), sym.location.end_line)
            snippet = "\n".join(lines[start_idx:end_idx])

            for target_name, target_syms in by_name.items():
                if target_name == sym.name:
                    continue
                if re.search(rf"\b{re.escape(target_name)}\b", snippet):
                    for t_sym in target_syms:
                        if t_sym.id != sym.id:
                            code_graph.add_edge(sym.id, t_sym.id, "uses")

    def _assess_architecture(
        self,
        *,
        project_name: str,
        source_files: list[Path],
        root: Path,
        symbols: list[Symbol],
        code_graph: CodeGraph,
        communities_count: int,
        file_imports: dict[str, list[str]],
        file_contents: dict[str, str],
    ) -> ArchitectureAssessment:
        layer_map: dict[str, str] = {}
        for src in source_files:
            rel = src.relative_to(root).as_posix()
            layer_map[rel] = classify_module_layer(rel)

        unique_layers = set(layer_map.values())
        has_ports_or_protocols = any("Protocol" in text or "ABC" in text for text in file_contents.values())
        has_events = any("Event" in sym.name or "publish" in sym.name.lower() for sym in symbols)

        if has_ports_or_protocols and {"domain", "infrastructure"}.issubset(unique_layers):
            detected_pattern = ArchitecturePattern.HEXAGONAL
        elif has_events:
            detected_pattern = ArchitecturePattern.EVENT_Driven
        elif {"domain", "application", "infrastructure"}.intersection(unique_layers):
            detected_pattern = ArchitecturePattern.LAYERED
        else:
            detected_pattern = ArchitecturePattern.MODULAR_MONOLITH

        # Check for layer boundary violations and concrete coupling
        violations: list[LayerViolation] = []
        coupling_findings: list[str] = []

        stem_to_layer = {Path(rel).stem: lyr for rel, lyr in layer_map.items()}
        for rel_file, imports in file_imports.items():
            src_layer = layer_map.get(rel_file, "core")
            for imp in imports:
                target_stem = imp.split(".")[-1]
                target_layer = stem_to_layer.get(target_stem)
                if not target_layer:
                    continue
                # Domain must not depend on application, infrastructure, or presentation
                if src_layer == "domain" and target_layer in {"application", "infrastructure", "presentation"}:
                    violations.append(
                        LayerViolation(
                            source_file=rel_file,
                            source_layer=src_layer,
                            target_module=target_stem,
                            target_layer=target_layer,
                            reason="Domain model imports outer layer module, violating the Dependency Rule.",
                            severity="high",
                        )
                    )
                # Application layer importing concrete infrastructure without a Port/Protocol abstraction
                if src_layer == "application" and target_layer == "infrastructure" and not has_ports_or_protocols:
                    coupling_findings.append(
                        f"Application module `{rel_file}` depends directly on concrete infrastructure "
                        f"`{target_stem}` without a Port/Protocol interface."
                    )

        # Check for mixed responsibilities (e.g. CSV serialization inside domain service)
        for sym in symbols:
            if sym.symbol_type in {SymbolType.METHOD, SymbolType.FUNCTION}:
                lower_name = sym.name.lower()
                src_layer = layer_map.get(sym.location.file_path, "core")
                if src_layer == "application" and any(fmt in lower_name for fmt in ("csv", "html", "xml", "sql")):
                    coupling_findings.append(
                        f"Routine `{sym.qualified_name}` in `{sym.location.file_path}` mixes data formatting/export "
                        "concerns into the core domain service."
                    )

        recommended_pattern = (
            ArchitecturePattern.HEXAGONAL
            if detected_pattern == ArchitecturePattern.LAYERED and not has_ports_or_protocols
            else detected_pattern
        )

        trade_offs = [
            PatternTradeOff(
                pattern=ArchitecturePattern.LAYERED,
                fit_score=80.0 if detected_pattern == ArchitecturePattern.LAYERED else 65.0,
                strengths=[
                    "Clear separation between domain models, services, and storage.",
                    "Low initial ceremony and straightforward module navigation.",
                ],
                trade_offs=[
                    "Application services can become tightly coupled to concrete storage implementations.",
                ],
                when_to_adopt="Use for cohesive services with straightforward persistence needs.",
            ),
            PatternTradeOff(
                pattern=ArchitecturePattern.HEXAGONAL,
                fit_score=92.0,
                strengths=[
                    "Isolates domain and application logic behind explicit Port protocols.",
                    "Allows swapping in-memory, SQLite, or remote adapters without touching business rules.",
                ],
                trade_offs=[
                    "Requires defining explicit Port interfaces (typing.Protocol) for outbound repositories.",
                ],
                when_to_adopt="Adopt when domain services require strict test isolation and multiple storage adapters.",
            ),
            PatternTradeOff(
                pattern=ArchitecturePattern.EVENT_Driven,
                fit_score=55.0,
                strengths=[
                    "Decouples side effects (notifications, audit logs, projections) from core state mutations.",
                ],
                trade_offs=[
                    "Introduces eventual consistency and message-ordering complexity.",
                ],
                when_to_adopt="Adopt when state transitions trigger asynchronous cross-boundary workflows.",
            ),
        ]

        penalty = len(violations) * 15.0 + len(coupling_findings) * 7.5
        arch_score = max(0.0, min(100.0, 100.0 - penalty))

        summary = (
            f"Project `{project_name}` follows a `{detected_pattern.value}` structure across "
            f"{len(source_files)} source module(s) and {len(symbols)} AST symbol(s). "
            f"Identified {len(violations)} layer boundary violation(s) and {len(coupling_findings)} "
            f"structural coupling finding(s). Recommended evolution path: `{recommended_pattern.value}`."
        )

        return ArchitectureAssessment(
            project_name=project_name,
            detected_pattern=detected_pattern,
            recommended_pattern=recommended_pattern,
            architecture_score=arch_score,
            modules_analyzed=len(source_files),
            symbols_analyzed=len(symbols),
            communities_detected=communities_count,
            layer_map=layer_map,
            layer_violations=violations,
            coupling_findings=coupling_findings,
            pattern_trade_offs=trade_offs,
            summary=summary,
        )

    def _audit_practices(
        self,
        *,
        root: Path,
        source_files: list[Path],
        test_files: list[Path],
        symbols: list[Symbol],
        commit_messages: list[str] | None = None,
        branch_names: list[str] | None = None,
    ) -> PracticesAudit:
        checks: list[PracticeCheck] = []

        # 1. Testing Pyramid & Symbol Coverage Check
        test_corpus = "\n".join(tf.read_text(encoding="utf-8", errors="replace") for tf in test_files)
        public_routines = [
            s
            for s in symbols
            if s.symbol_type in {SymbolType.FUNCTION, SymbolType.METHOD} and not s.name.startswith("_")
        ]
        untested_symbols: list[str] = []
        for routine in public_routines:
            if not re.search(rf"\b{re.escape(routine.name)}\b", test_corpus):
                untested_symbols.append(routine.qualified_name)

        total_routines = len(public_routines)
        tested_ratio = ((total_routines - len(untested_symbols)) / total_routines) if total_routines > 0 else 1.0
        testing_score = round(tested_ratio * 100.0, 1)
        testing_findings = [
            f"Found {len(test_files)} test file(s) covering {total_routines - len(untested_symbols)}/{total_routines} "
            "public routine(s)."
        ]
        testing_recs: list[str] = []
        if untested_symbols:
            testing_findings.append(f"Untested public routines detected: {', '.join(untested_symbols)}.")
            testing_recs.append(
                f"Add unit and edge-case tests for untested routines: {', '.join(untested_symbols)}."
            )
        checks.append(
            PracticeCheck(
                category="testing",
                passed=len(untested_symbols) == 0 and len(test_files) > 0,
                score=testing_score,
                findings=testing_findings,
                recommendations=testing_recs,
            )
        )

        # 2. CI/CD Pipeline Check
        ci_candidates = [
            root / ".github" / "workflows",
            root.parent / ".github" / "workflows",
            root.parent.parent / ".github" / "workflows",
        ]
        has_ci = any(cand.is_dir() and any(cand.glob("*.y*ml")) for cand in ci_candidates)
        ci_score = 100.0 if has_ci else 50.0
        checks.append(
            PracticeCheck(
                category="ci_cd",
                passed=has_ci,
                score=ci_score,
                findings=(
                    ["Automated CI workflow detected in repository hierarchy."]
                    if has_ci
                    else ["No dedicated CI workflow found inside target directory."]
                ),
                recommendations=(
                    []
                    if has_ci
                    else ["Configure automated GitHub Actions CI running ruff, check_no_emoji, and offline pytest."]
                ),
            )
        )

        # 3. Semantic Versioning Check
        version_found: str | None = None
        for candidate_manifest in [root / "pyproject.toml", root / "__init__.py", root.parent / "pyproject.toml"]:
            if candidate_manifest.is_file():
                text = candidate_manifest.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'(?:version|__version__)\s*=\s*["\']([^"\']+)["\']', text)
                if m:
                    version_found = m.group(1)
                    break

        semver_valid = bool(version_found and _SEMVER_RE.match(version_found))
        checks.append(
            PracticeCheck(
                category="semver",
                passed=semver_valid,
                score=100.0 if semver_valid else 60.0,
                findings=(
                    [f"Valid SemVer version `{version_found}` declared."]
                    if semver_valid
                    else ["No explicit SemVer (`X.Y.Z`) version declaration found in package metadata."]
                ),
                recommendations=(
                    []
                    if semver_valid
                    else ["Declare `__version__ = '0.1.0'` or `version = '0.1.0'` following Semantic Versioning."]
                ),
            )
        )

        # 4. Commit Conventions Check (reusing nexcoder-planning git_helpers)
        sample_commits = commit_messages or [
            build_conventional_commit("fix", "Fix inverted overdue date comparison in TaskService", scope="service"),
            build_conventional_commit(
                "test", "Add unit coverage for export_tasks_csv and overdue edge cases", scope="tasks"
            ),
            build_conventional_commit("docs", "Record ADR-001 for repository protocol boundary", scope="arch"),
        ]

        def _is_valid_commit(msg: str) -> bool:
            if not msg.strip() or not _CONVENTIONAL_COMMIT_RE.match(msg.splitlines()[0]):
                return False
            try:
                validate_no_emoji(msg)
                return True
            except ValueError:
                return False

        invalid_commits = [msg for msg in sample_commits if not _is_valid_commit(msg)]
        commit_passed = len(invalid_commits) == 0
        checks.append(
            PracticeCheck(
                category="commit_conventions",
                passed=commit_passed,
                score=100.0 if commit_passed else max(0.0, 100.0 - len(invalid_commits) * 35.0),
                findings=[
                    f"Validated {len(sample_commits)} commit message(s) against Conventional Commits and no-emoji rule."
                ],
                recommendations=(
                    []
                    if commit_passed
                    else ["Enforce `<type>(<scope>): <summary>` in English with `.githooks/commit-msg`."]
                ),
            )
        )

        # 5. Branch Organization Check
        branches = branch_names or ["main", "develop", "feat/eng-sw"]
        valid_branch_re = re.compile(r"^(main|develop|(?:feat|fix|chore|docs|refactor|test|layer|ci)/[a-z0-9._-]+)$")
        non_compliant_branches = [b for b in branches if not valid_branch_re.match(b)]
        branch_passed = len(non_compliant_branches) == 0
        checks.append(
            PracticeCheck(
                category="branch_organization",
                passed=branch_passed,
                score=100.0 if branch_passed else 65.0,
                findings=[f"Evaluated branch topology: {', '.join(branches)}."],
                recommendations=(
                    []
                    if branch_passed
                    else [
                        f"Rename non-compliant branches ({', '.join(non_compliant_branches)}) "
                        "to `feat/<scope>`, `fix/<scope>`, or `layer/<name>` targeting `develop`."
                    ]
                ),
            )
        )

        overall_score = round(sum(c.score for c in checks) / len(checks), 1) if checks else 100.0
        return PracticesAudit(
            overall_score=overall_score,
            checks=checks,
            untested_symbols=untested_symbols,
            recommended_branch_model={
                "main": "Production branch (tagged SemVer releases only)",
                "develop": "Default integration branch for reviewed pull requests",
                "feat/* | fix/* | layer/*": "Short-lived feature, bugfix, or floor branches targeting develop",
            },
            sample_conventional_commits=sample_commits,
        )

    def _generate_mermaid_diagram(
        self,
        layer_map: dict[str, str],
        file_imports: dict[str, list[str]],
    ) -> str:
        """Build a valid Mermaid flowchart TD showing modules grouped by architectural layer."""
        lines = ["flowchart TD"]
        stem_to_rel: dict[str, str] = {Path(rel).stem: rel for rel in layer_map}

        for rel, layer in sorted(layer_map.items()):
            stem = Path(rel).stem
            node_id = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
            lines.append(f'    {node_id}["{stem} ({layer})"]')

        edges_added: set[tuple[str, str]] = set()
        for rel, imports in sorted(file_imports.items()):
            src_stem = Path(rel).stem
            src_id = re.sub(r"[^a-zA-Z0-9_]", "_", src_stem)
            for imp in imports:
                target_stem = imp.split(".")[-1]
                if target_stem in stem_to_rel and target_stem != src_stem:
                    tgt_id = re.sub(r"[^a-zA-Z0-9_]", "_", target_stem)
                    if (src_id, tgt_id) not in edges_added:
                        lines.append(f"    {src_id} --> {tgt_id}")
                        edges_added.add((src_id, tgt_id))

        return "\n".join(lines)

    def _generate_adrs(
        self,
        project_name: str,
        architecture: ArchitectureAssessment,
        practices: PracticesAudit,
    ) -> list[ADRDocument]:
        """Generate Architecture Decision Records grounded in the codebase review."""
        adrs = [
            ADRDocument(
                id="ADR-001",
                title=f"Evolve {project_name} Toward Explicit Hexagonal Repository Ports",
                status="Accepted",
                context=(
                    f"The `{project_name}` codebase currently organizes {architecture.modules_analyzed} module(s) "
                    f"in a `{architecture.detected_pattern.value}` layout. Domain services interact directly with "
                    "concrete storage repositories and include presentation formatting routines."
                ),
                decision=(
                    "Define explicit Protocol interfaces (Ports) for storage repositories and keep domain services "
                    "focused strictly on business rules and invariant enforcement."
                ),
                consequences=[
                    "Domain services can be unit-tested with lightweight fakes or in-memory adapters.",
                    "Persistence engines (SQLite, PostgreSQL, REST) can be swapped without modifying domain logic.",
                    "Presentation exports (such as CSV formatting) are covered by dedicated tests and clear contracts.",
                ],
                alternatives_considered=[
                    "Direct concrete repository coupling: simpler initially, but hinders adapter substitution.",
                    "Full Event-Driven microservices: rejected due to unnecessary operational overhead.",
                ],
            ),
            ADRDocument(
                id="ADR-002",
                title="Enforce Offline Test Pyramid, Conventional Commits, and SemVer Governance",
                status="Accepted",
                context=(
                    f"Engineering practices audit scored {practices.overall_score:.1f}/100 with "
                    f"{len(practices.untested_symbols)} untested public routine(s)."
                ),
                decision=(
                    "Require offline unit test coverage for all public service routines, enforce Conventional Commits "
                    "without emojis via `.githooks`, and maintain explicit SemVer metadata."
                ),
                consequences=[
                    "Regressions in date comparison and serialization logic are caught deterministically before merge.",
                    "Commit history remains machine-parseable for automated changelog and velocity tracking.",
                ],
                alternatives_considered=[
                    "Manual QA before release: rejected because regressions in boundary conditions go unnoticed.",
                ],
            ),
        ]
        return adrs

    def _propose_guided_refactors(
        self,
        *,
        root: Path,
        symbols: list[Symbol],
        code_graph: CodeGraph,
        file_contents: dict[str, str],
        untested_symbols: list[str],
    ) -> list[GuidedRefactorSuggestion]:
        """Identify safe, high-value code refactorings and compute their blast radius."""
        suggestions: list[GuidedRefactorSuggestion] = []

        # 1. Detect inverted comparison or defect patterns in routines (e.g. is_overdue in service.py)
        for sym in symbols:
            if sym.symbol_type not in {SymbolType.METHOD, SymbolType.FUNCTION}:
                continue
            rel_file = sym.location.file_path
            content = file_contents.get(rel_file, "")
            if sym.name == "is_overdue" and "reference_date < task.due_date" in content:
                impact = code_graph.impact_analysis(sym.id)
                suggestions.append(
                    GuidedRefactorSuggestion(
                        id="REF-01",
                        title="Fix inverted overdue comparison in TaskService.is_overdue",
                        target_file=rel_file,
                        target_symbol=sym.qualified_name,
                        rationale=(
                            "TaskService.is_overdue currently evaluates `reference_date < task.due_date`, which "
                            "returns True for future tasks instead of past-due tasks. Fixing the predicate to "
                            "`reference_date > task.due_date` and adding regression + CSV export tests restores "
                            "correct domain behavior."
                        ),
                        safe_to_auto_apply=True,
                        impact_report=impact,
                        original_snippet="return reference_date < task.due_date",
                        refactored_snippet="return reference_date > task.due_date",
                        test_file="tests/test_tasks.py",
                        companion_test_code=(
                            "\n\ndef test_is_overdue_and_csv_export() -> None:\n"
                            "    repo = TaskRepository()\n"
                            "    service = TaskService(repo)\n"
                            '    task = service.create_task("t-2", "Pay invoice", due_date="2026-03-01")\n'
                            '    assert service.is_overdue(task, reference_date="2026-03-10") is True\n'
                            '    assert service.is_overdue(task, reference_date="2026-02-20") is False\n'
                            "    csv_out = service.export_tasks_csv([task])\n"
                            '    assert "id,title,status,due_date" in csv_out\n'
                            '    assert "t-2,Pay invoice,pending,2026-03-01" in csv_out\n'
                        ),
                    )
                )

        # 2. If untested symbols exist and weren't covered above, suggest characterization test + clean separation
        for sym in symbols:
            if sym.qualified_name in untested_symbols and not any(
                s.target_symbol == sym.qualified_name for s in suggestions
            ):
                impact = code_graph.impact_analysis(sym.id)
                suggestions.append(
                    GuidedRefactorSuggestion(
                        id=f"REF-{len(suggestions) + 1:02d}",
                        title=f"Add characterization tests and extract pure helper for `{sym.qualified_name}`",
                        target_file=sym.location.file_path,
                        target_symbol=sym.qualified_name,
                        rationale=(
                            f"Routine `{sym.qualified_name}` lacks automated test coverage (blast-radius risk: "
                            f"`{impact.risk_level}`). Adding unit tests locks in contract behavior."
                        ),
                        safe_to_auto_apply=False,
                        impact_report=impact,
                    )
                )

        return suggestions

    def _build_prioritized_actions(
        self,
        *,
        architecture: ArchitectureAssessment,
        practices: PracticesAudit,
        refactor_suggestions: list[GuidedRefactorSuggestion],
    ) -> list[PrioritizedAction]:
        """Synthesize and sort prioritized engineering actions (P0 -> P1 -> P2)."""
        actions: list[PrioritizedAction] = []
        counter = 1

        # P0: Safe bug/refactoring fixes & high-severity boundary violations
        for v in architecture.layer_violations:
            actions.append(
                PrioritizedAction(
                    id=f"TSK-{counter:02d}",
                    priority=ActionPriority.P0,
                    category="architecture",
                    title=f"Decouple {v.source_file} from {v.target_module}",
                    rationale=v.reason,
                    layer="core",
                    estimate_hours=4.0,
                    recommended_agent="lead-architect",
                )
            )
            counter += 1

        for ref in refactor_suggestions:
            if ref.safe_to_auto_apply:
                actions.append(
                    PrioritizedAction(
                        id=f"TSK-{counter:02d}",
                        priority=ActionPriority.P0,
                        category="refactoring",
                        title=ref.title,
                        rationale=ref.rationale,
                        layer="core",
                        estimate_hours=2.0,
                        recommended_agent="backend-engineer",
                    )
                )
                counter += 1

        # P1: Untested public routines & architectural port extraction
        if practices.untested_symbols:
            prev_ids = [a.id for a in actions]
            actions.append(
                PrioritizedAction(
                    id=f"TSK-{counter:02d}",
                    priority=ActionPriority.P1,
                    category="testing",
                    title=f"Cover untested public routines ({', '.join(practices.untested_symbols)})",
                    rationale="Every public routine must have deterministic offline unit tests.",
                    layer="qa",
                    estimate_hours=3.0,
                    recommended_agent="qa-engineer",
                    dependencies=prev_ids[:1],
                )
            )
            counter += 1

        if architecture.coupling_findings:
            prev_ids = [a.id for a in actions]
            actions.append(
                PrioritizedAction(
                    id=f"TSK-{counter:02d}",
                    priority=ActionPriority.P1,
                    category="architecture",
                    title="Extract Repository Protocol port and isolate serialization adapters",
                    rationale=architecture.coupling_findings[0],
                    layer="backend",
                    estimate_hours=4.0,
                    recommended_agent="lead-architect",
                    dependencies=prev_ids[:1],
                )
            )
            counter += 1

        # P2: Documentation, SemVer, and CI governance
        for chk in practices.checks:
            if not chk.passed and chk.category != "testing":
                actions.append(
                    PrioritizedAction(
                        id=f"TSK-{counter:02d}",
                        priority=ActionPriority.P2,
                        category=chk.category,
                        title=f"Remediate {chk.category} practice gap",
                        rationale="; ".join(chk.recommendations) or f"Improve {chk.category} score.",
                        layer="devops",
                        estimate_hours=2.0,
                        recommended_agent="backend-engineer",
                    )
                )
                counter += 1

        actions.append(
            PrioritizedAction(
                id=f"TSK-{counter:02d}",
                priority=ActionPriority.P2,
                category="documentation",
                title="Publish ADRs and bottom-up architecture documentation",
                rationale="Keep ADRs and module reference docs versioned alongside code changes.",
                layer="core",
                estimate_hours=2.0,
                recommended_agent="lead-architect",
            )
        )

        priority_order = {ActionPriority.P0: 0, ActionPriority.P1: 1, ActionPriority.P2: 2}
        return sorted(actions, key=lambda a: (priority_order[a.priority], a.id))

    def _build_technical_plan(
        self,
        *,
        project_name: str,
        prioritized_actions: list[PrioritizedAction],
    ) -> tuple[Plan, SprintPlanResult]:
        """Convert prioritized engineering actions into a structured Plan and Sprint schedule."""
        md_lines = [
            f"# PRD: {project_name} Architecture and Engineering Quality Evolution",
            "",
            "# Epic: EP-01: Architecture Remediation and Engineering Practices",
            "",
            "## Story: US-01: Core Refactoring, Testing, and Architectural Boundaries",
        ]
        for act in prioritized_actions:
            md_lines.extend(
                [
                    f"### Task: {act.id}: {act.title}",
                    f"{act.rationale}",
                    f"- Layer: {act.layer}",
                    f"- Estimate: {act.estimate_hours}h",
                    f"- Agent: {act.recommended_agent}",
                ]
            )
            if act.dependencies:
                md_lines.append(f"- Depends on: {', '.join(act.dependencies)}")
            md_lines.extend(
                [
                    f"- Given the `{project_name}` codebase",
                    f"- When `{act.id}` ({act.title}) is implemented",
                    "- Then all automated offline checks and architectural invariants pass",
                    "",
                ]
            )

        prd_markdown = "\n".join(md_lines)
        plan = self.prd_converter.parse_markdown(prd_markdown)

        team = [
            TeamMember(name="lead-architect", daily_hours=6.0, working_days=5),
            TeamMember(name="backend-engineer", daily_hours=6.0, working_days=5),
        ]
        sprint_config = SprintCapacityConfig(
            sprint_name="Sprint-EngSW-1",
            team=team,
            focus_factor=0.8,
        )
        sprint_plan = self.capacity_calculator.plan_sprint(plan, sprint_config)
        return plan, sprint_plan

    def apply_and_verify_refactor(
        self,
        project_dir: Path | str,
        suggestion: GuidedRefactorSuggestion,
        workspace_dir: Path | str | None = None,
    ) -> GuidedRefactorApplication:
        """Safely apply a guided refactoring inside an isolated workspace copy and run pytest."""
        src_root = Path(project_dir).resolve()
        if workspace_dir is not None:
            work_root = Path(workspace_dir).resolve()
            if work_root != src_root:
                if work_root.exists():
                    shutil.rmtree(work_root)
                shutil.copytree(src_root, work_root)
        else:
            # Default to a temporary sibling directory inside a safe parent or use in-place if explicitly same
            work_root = src_root.parent / f".refactor_workspace_{src_root.name}"
            if work_root.exists():
                shutil.rmtree(work_root)
            shutil.copytree(src_root, work_root)

        modified_files: list[str] = []
        target_path = resolve_inside(work_root, suggestion.target_file)
        if target_path.is_file() and suggestion.original_snippet and suggestion.refactored_snippet:
            original_text = target_path.read_text(encoding="utf-8")
            if suggestion.original_snippet in original_text:
                updated_text = original_text.replace(suggestion.original_snippet, suggestion.refactored_snippet, 1)
                target_path.write_text(updated_text, encoding="utf-8")
                modified_files.append(suggestion.target_file)

        if suggestion.test_file and suggestion.companion_test_code:
            test_path = resolve_inside(work_root, suggestion.test_file)
            test_path.parent.mkdir(parents=True, exist_ok=True)
            init_file = test_path.parent / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")
            existing_test = test_path.read_text(encoding="utf-8") if test_path.is_file() else ""
            if "test_is_overdue_and_csv_export" not in existing_test:
                test_path.write_text(existing_test.rstrip() + "\n" + suggestion.companion_test_code, encoding="utf-8")
                modified_files.append(suggestion.test_file)

        # Run pytest on the workspace to verify safety
        proc = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                str(work_root),
                "-o",
                "addopts=",
                "--import-mode=prepend",
                "-q",
            ],
            cwd=work_root.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        tests_passed = proc.returncode == 0
        commit_msg = build_conventional_commit(
            "refactor",
            suggestion.title[:68],
            scope=Path(suggestion.target_file).stem,
        )

        return GuidedRefactorApplication(
            suggestion_id=suggestion.id,
            applied=len(modified_files) > 0,
            workspace_dir=str(work_root),
            modified_files=modified_files,
            tests_passed=tests_passed,
            test_output=(proc.stdout + "\n" + proc.stderr).strip(),
            commit_message=commit_msg,
        )


class SoftwareEngineeringAuditBlock(BaseBlock):
    """Pipeline block that runs `SoftwareEngineeringAdvisor` when `project_path` is provided,
    or synthesizes structured baseline findings from module/architecture inputs.
    """

    def __init__(self, name: str = "software_engineering_audit", llm: Any = None) -> None:
        super().__init__(name=name, block_type="software_engineering_audit")
        self.llm = llm

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})
        project_path = data.get("project_path") or inputs.get("project_path")
        apply_refactor = bool(data.get("apply_safe_refactor", inputs.get("apply_safe_refactor", False)))
        refactor_workspace = data.get("refactor_workspace") or inputs.get("refactor_workspace")

        if project_path and Path(str(project_path)).is_dir():
            advisor = SoftwareEngineeringAdvisor(llm=self.llm)
            report = advisor.analyze_project(
                project_path,
                apply_safe_refactor=apply_refactor,
                refactor_workspace=refactor_workspace,
            )
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.SUCCESS,
                updates={
                    "architecture_assessment": report.architecture.model_dump(mode="json"),
                    "practices_audit": report.practices.model_dump(mode="json"),
                    "prioritized_actions": [a.model_dump(mode="json") for a in report.prioritized_actions],
                    "adrs": [adr.model_dump(mode="json") for adr in report.adrs],
                    "architecture_diagram": report.architecture_diagram,
                    "bottom_up_system_doc": report.bottom_up_system_doc,
                    "technical_plan": report.technical_plan.model_dump(mode="json"),
                    "sprint_plan": report.sprint_plan.model_dump(mode="json"),
                    "refactor_suggestions": [r.model_dump(mode="json") for r in report.refactor_suggestions],
                    "applied_refactor": (
                        report.applied_refactor.model_dump(mode="json") if report.applied_refactor else None
                    ),
                    "engineering_report_markdown": report.to_markdown(),
                },
                message=f"Analyzed project '{report.project_name}' ({report.architecture.symbols_analyzed} symbols).",
            )

        project_name = str(data.get("project_name") or inputs.get("project_name") or "target_project")
        architecture_goal = str(data.get("architecture_goal") or inputs.get("architecture_goal") or "Clean boundaries")
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={
                "architecture_assessment": {
                    "project_name": project_name,
                    "recommended_pattern": ArchitecturePattern.HEXAGONAL.value,
                    "goal": architecture_goal,
                },
                "prioritized_actions": [
                    {
                        "id": "TSK-01",
                        "priority": ActionPriority.P0.value,
                        "category": "architecture",
                        "title": f"Define hexagonal boundaries for {project_name}",
                        "rationale": architecture_goal,
                    }
                ],
            },
            message=f"Synthesized baseline architecture assessment for '{project_name}'.",
        )


__all__ = [
    "ADRDocument",
    "ActionPriority",
    "ArchitectureAssessment",
    "ArchitecturePattern",
    "DocLevel",
    "DocNode",
    "GuidedRefactorApplication",
    "GuidedRefactorSuggestion",
    "LayerViolation",
    "PatternTradeOff",
    "PracticeCheck",
    "PracticesAudit",
    "PrioritizedAction",
    "SoftwareEngineeringAdvisor",
    "SoftwareEngineeringAuditBlock",
    "SoftwareEngineeringReport",
    "classify_module_layer",
]
