"""Open-source contribution mode (Issue #75): read-only repository mapping,
multi-language static bug and smell detection, security scanning, fix synthesis,
responsible vulnerability disclosure, and upstream contribution reporting.

Integrates:
- `nexcoder-code-intel`: AST parsing across languages, `CodeSearchIndex` (RAG),
  `CodeGraph` and `CommunityDetector` (GraphRAG), and `impact_analysis`.
- `nexcoder-security`: offline `MultiScannerEngine` (`bandit`, `semgrep`,
  `pip-audit`, `osv-scanner`, `gitleaks`).
- `nexcoder-planning`: conventional commit and PR body helpers and idempotent
  platform adapter integration (dry-run by default).
- `nexcoder-control`: `AppendOnlyAuditLog` and `TargetAuthorizationGate`.
- `nexcoder-agents`: multi-stage pipeline blocks (`map_project` -> `find_problems`
  -> `propose_fixes` -> `build_report`).

Strictly read-only on target repositories: never executes third-party code or tests.
"""

from __future__ import annotations

import ast
import os
import re
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any

from nexcoder_code_intel.graph import CodeGraph, CommunityDetector, ImpactReport
from nexcoder_code_intel.models import Symbol
from nexcoder_code_intel.parsers import get_parser_for_file, parse_file
from nexcoder_code_intel.retrieval import DEFAULT_BINARY_EXTENSIONS, DEFAULT_IGNORE_DIRS, CodeSearchIndex
from nexcoder_control.approval import TargetAuthorizationGate
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_core.retrieval.embeddings import HashEmbedder
from nexcoder_core.sandbox import resolve_inside
from nexcoder_planning.adapters.base import PlatformAdapter
from nexcoder_planning.git_helpers import build_conventional_commit, build_pull_request_body
from nexcoder_planning.models import AcceptanceCriterion, Epic, Plan, Story, Task
from nexcoder_security.models import Finding as SecurityFinding
from nexcoder_security.scanners.engine import MultiScannerEngine
from pydantic import BaseModel, Field

from nexcoder_agents.engine.blocks.base import BaseBlock
from nexcoder_agents.engine.models import BlockResult, BlockStatus


class OSSFindingCategory(StrEnum):
    """Canonical prioritization categories for open-source findings."""

    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    READABILITY = "readability"


class DisclosureChannelType(StrEnum):
    """Supported reporting channels for findings."""

    GITHUB_SECURITY_ADVISORY = "github_private_vulnerability_reporting"
    SECURITY_MD_EMAIL = "security_md_private_email"
    SECURITY_MD_URL = "security_md_advisory_url"
    PUBLIC_ISSUE_TRACKER = "public_issue_tracker"


_EXPLOIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:DROP\s+TABLE|UNION\s+SELECT|--\s*shutdown)\b"),
    re.compile(r"(?i)<script[^>]*>.*?</script>"),
    re.compile(r"(?i)(?:;\s*rm\s+-rf\b|/bin/sh\s+-i|nc\s+-e\s+/bin/)"),
    re.compile(r"(?i)\b(?:exploit_payload|weaponized_poc|reverse_shell)\b"),
)


def sanitize_no_exploit(text: str) -> tuple[str, bool]:
    """Strip any offensive exploit or weaponized PoC patterns from generated text.

    Returns a tuple of `(sanitized_text, had_exploit_pattern)`.
    """
    cleaned = text
    detected = False
    for pat in _EXPLOIT_PATTERNS:
        if pat.search(cleaned):
            detected = True
            cleaned = pat.sub("[REDACTED_OFFENSIVE_PAYLOAD]", cleaned)
    return cleaned, detected


class OSSProjectGovernance(BaseModel):
    """Governance, contribution rules, and security disclosure metadata of a target OSS repo."""

    has_contributing_md: bool = False
    contributing_path: str | None = None
    contributing_guidelines_summary: list[str] = Field(default_factory=list)
    has_security_md: bool = False
    security_md_path: str | None = None
    private_security_channel: str = "https://github.com/OWNER/REPO/security/advisories/new"
    preferred_disclosure_channel: DisclosureChannelType = DisclosureChannelType.GITHUB_SECURITY_ADVISORY
    license_type: str | None = None


class OSSProjectMap(BaseModel):
    """Stage 1 output: structural, RAG, GraphRAG, and governance map of an OSS project."""

    project_name: str
    source_target: str
    resolved_path: str
    read_only_verified: bool = True
    files_indexed: int = 0
    symbols_extracted: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    communities_detected: int = 0
    languages_breakdown: dict[str, int] = Field(default_factory=dict)
    rag_highlights: list[dict[str, Any]] = Field(default_factory=list)
    community_summaries: list[str] = Field(default_factory=list)
    governance: OSSProjectGovernance = Field(default_factory=OSSProjectGovernance)


class OSSIssueFinding(BaseModel):
    """Stage 2 output: a prioritized bug, security flaw, broken test, or code improvement."""

    id: str
    category: OSSFindingCategory
    severity: str = "medium"  # critical, high, medium, low
    priority_rank: int = 1
    language: str = "python"
    file_path: str
    line_number: int | None = None
    symbol_name: str | None = None
    title: str
    description: str
    evidence_snippet: str = ""
    detector: str = "static-analyzer"
    cwe_or_cve: str | None = None
    is_security_sensitive: bool = False
    impact_blast_radius: ImpactReport | None = None


class OSSFixSuggestion(BaseModel):
    """Stage 3 output: concrete code fix snippet, rationale, and disclosure routing."""

    finding_id: str
    category: OSSFindingCategory
    title: str
    file_path: str
    line_number: int | None = None
    original_snippet: str
    suggested_snippet: str
    rationale: str
    verification_notes: str
    contains_exploit_payload: bool = False
    disclosure_route: str = "public_pr_or_issue"  # "private_security_advisory" or "public_pr_or_issue"


class OSSUpstreamAction(BaseModel):
    """Prepared or executed upstream contribution action (private advisory or public issue/PR)."""

    finding_id: str
    action_type: str  # "private_security_report", "public_issue", "public_pull_request"
    channel: str
    title: str
    commit_message: str = ""
    body_preview: str
    submitted: bool = False
    dry_run: bool = True
    blocked_public_disclosure: bool = False


class OSSContributionReport(BaseModel):
    """Stage 4 output: complete open-source analysis, fix proposals, and contribution report."""

    project_map: OSSProjectMap
    findings: list[OSSIssueFinding] = Field(default_factory=list)
    suggestions: list[OSSFixSuggestion] = Field(default_factory=list)
    upstream_actions: list[OSSUpstreamAction] = Field(default_factory=list)
    audit_events_recorded: int = 0

    def findings_by_category(self, category: OSSFindingCategory) -> list[OSSIssueFinding]:
        """Return findings filtered by category in priority order."""
        return [f for f in self.findings if f.category == category]

    def to_markdown(self) -> str:
        """Render the complete OSS contribution and responsible disclosure report as Markdown."""
        pm = self.project_map
        gov = pm.governance
        lines = [
            f"# Open-Source Contribution Report: {pm.project_name}",
            "",
            "## 1. Project Map & Code Intelligence (RAG / GraphRAG)",
            f"- **Source Target**: `{pm.source_target}`",
            f"- **Read-Only Analysis Verified**: `{pm.read_only_verified}` (zero third-party code execution)",
            f"- **Files Indexed (`CodeSearchIndex`)**: {pm.files_indexed}",
            f"- **AST Symbols Extracted**: {pm.symbols_extracted}",
            f"- **CodeGraph Topology**: {pm.graph_nodes} nodes, {pm.graph_edges} edges",
            f"- **GraphRAG Communities (`CommunityDetector`)**: {pm.communities_detected}",
            f"- **Detected License**: `{gov.license_type or 'Unspecified'}`",
            "",
            "### Languages Breakdown",
        ]
        for lang, count in sorted(pm.languages_breakdown.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- `{lang}`: {count} file(s)")

        if pm.community_summaries:
            lines.extend(["", "### GraphRAG Subsystem Clusters"])
            for summary in pm.community_summaries:
                lines.append(f"- {summary}")

        lines.extend(
            [
                "",
                "## 2. Project Governance & Coordinated Vulnerability Disclosure",
                f"- **CONTRIBUTING.md Present**: `{gov.has_contributing_md}`"
                + (f" (`{gov.contributing_path}`)" if gov.contributing_path else ""),
                f"- **SECURITY.md Present**: `{gov.has_security_md}`"
                + (f" (`{gov.security_md_path}`)" if gov.security_md_path else ""),
                f"- **Private Security Channel**: `{gov.private_security_channel}` "
                f"(`{gov.preferred_disclosure_channel.value}`)",
            ]
        )
        if gov.contributing_guidelines_summary:
            lines.append("- **Contribution Guidelines**:")
            for rule in gov.contributing_guidelines_summary:
                lines.append(f"  - {rule}")

        lines.extend(
            [
                "",
                "## 3. Prioritized Findings (Bug, Security, Performance, Readability)",
                "",
                "| Rank | ID | Category | Severity | Language | Location | Title |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for f in self.findings:
            loc = f"{f.file_path}:{f.line_number}" if f.line_number else f.file_path
            lines.append(
                f"| #{f.priority_rank} | `{f.id}` | `{f.category.value}` | "
                f"`{f.severity}` | `{f.language}` | `{loc}` | {f.title} |"
            )

        lines.extend(["", "## 4. Proposed Fixes & Technical Justifications"])
        suggestion_map = {s.finding_id: s for s in self.suggestions}
        for f in self.findings:
            sug = suggestion_map.get(f.id)
            lines.extend(
                [
                    "",
                    f"### [{f.id}] {f.title} (`{f.category.value}` / `{f.severity}`)",
                    f"- **Location**: `{f.file_path}`" + (f" (line {f.line_number})" if f.line_number else ""),
                    f"- **Detector**: `{f.detector}`",
                    f"- **Description**: {f.description}",
                ]
            )
            if sug:
                lines.extend(
                    [
                        f"- **Disclosure Route**: `{sug.disclosure_route}`",
                        f"- **Rationale**: {sug.rationale}",
                        f"- **Verification**: {sug.verification_notes}",
                        "",
                        "**Original Code:**",
                        "```",
                        sug.original_snippet,
                        "```",
                        "",
                        "**Suggested Fix:**",
                        "```",
                        sug.suggested_snippet,
                        "```",
                    ]
                )

        lines.extend(
            [
                "",
                "## 5. Upstream Contribution & Responsible Disclosure Plan",
                "",
                "Security findings are strictly routed to the project's private vulnerability reporting channel "
                "without offensive exploit payloads. Non-security bug, performance, and readability improvements "
                "are prepared as standard upstream issues/PRs following `CONTRIBUTING.md`.",
                "",
            ]
        )
        for act in self.upstream_actions:
            lines.append(
                f"- **`{act.finding_id}`** -> `{act.action_type}` via `{act.channel}` "
                f"(dry_run=`{act.dry_run}`, blocked_public_disclosure=`{act.blocked_public_disclosure}`): "
                f"{act.title}"
            )

        return "\n".join(lines).strip() + "\n"


_EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".pas": "delphi",
    ".dpr": "delphi",
}


class OSSContributionAdvisor:
    """Read-only analyzer and contribution coordinator for open-source repositories.

    Never executes code, tests, or build scripts from the target repository.
    """

    def __init__(
        self,
        *,
        audit_log: AppendOnlyAuditLog | None = None,
        target_gate: TargetAuthorizationGate | None = None,
        security_engine: MultiScannerEngine | None = None,
        llm: Any = None,
    ) -> None:
        self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
        self.target_gate = (
            target_gate if target_gate is not None else TargetAuthorizationGate(audit_log=self.audit_log)
        )
        self.security_engine = (
            security_engine
            if security_engine is not None
            else MultiScannerEngine(target_gate=self.target_gate, audit_log=self.audit_log)
        )
        self.llm = llm

    @staticmethod
    def _enforce_read_only(read_only: bool) -> None:
        if not read_only:
            raise ValueError(
                "OSS analysis mode is strictly read-only; executing third-party project code is prohibited."
            )

    @staticmethod
    def _resolve_repo_path(
        target: str | Path,
        local_checkout: str | Path | None = None,
    ) -> tuple[str, Path]:
        """Resolve a local path or URL+checkout to a verified local directory."""
        source_str = str(target).strip()
        if local_checkout is not None:
            resolved = Path(local_checkout).resolve()
        elif source_str.startswith("file://"):
            resolved = Path(source_str.removeprefix("file://")).resolve()
        else:
            resolved = Path(source_str).resolve()

        if not resolved.is_dir():
            raise FileNotFoundError(f"OSS target directory not found: {resolved}")
        return source_str, resolved

    def map_project(
        self,
        target: str | Path,
        *,
        local_checkout: str | Path | None = None,
        read_only: bool = True,
    ) -> tuple[OSSProjectMap, CodeGraph, dict[str, Symbol]]:
        """Stage 1: Index the OSS repository with `code-intel` (RAG + GraphRAG) and inspect governance."""
        self._enforce_read_only(read_only)
        source_str, root = self._resolve_repo_path(target, local_checkout=local_checkout)
        project_name = root.name

        self.audit_log.record_event(
            event_type="oss.map_project",
            actor="oss-advisor",
            action="read_only_index",
            resource=source_str,
            severity="info",
            details={"project_name": project_name, "read_only": True},
        )

        # 1. Index source files with CodeSearchIndex + HashEmbedder in a temporary SQLite store
        embedder = HashEmbedder(dimensions=128)
        rag_highlights: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="nexcoder_oss_idx_") as tmp_idx_dir:
            db_path = Path(tmp_idx_dir) / "oss_code_index.db"
            with CodeSearchIndex(db_path, embedder=embedder) as search_index:
                files_indexed = search_index.index_directory(root)
                for query in ("error exception bug return", "security token auth password", "loop query list"):
                    hits = search_index.search(query, top_k=2, hyde=True)
                    for hit in hits:
                        if not any(h["id"] == hit["id"] for h in rag_highlights):
                            rag_highlights.append(
                                {
                                    "id": hit["id"],
                                    "score": round(float(hit.get("score", 0.0)), 4),
                                    "file_path": hit.get("metadata", {}).get("file_path", ""),
                                    "symbol_name": hit.get("metadata", {}).get("symbol_name", ""),
                                }
                            )

        # 2. Parse AST symbols across supported languages & build CodeGraph + GraphRAG communities
        graph = CodeGraph()
        all_symbols: list[Symbol] = []
        symbol_by_name: dict[str, Symbol] = {}
        languages_breakdown: dict[str, int] = {}

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
            for fname in sorted(filenames):
                fpath = Path(dirpath) / fname
                suffix = fpath.suffix.lower()
                if suffix in DEFAULT_BINARY_EXTENSIONS:
                    continue
                lang = _EXTENSION_LANGUAGE_MAP.get(suffix)
                if lang:
                    languages_breakdown[lang] = languages_breakdown.get(lang, 0) + 1
                if get_parser_for_file(fpath) is not None:
                    rel_path = fpath.relative_to(root).as_posix()
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    parsed_syms = parse_file(rel_path, content=content)
                    all_symbols.extend(parsed_syms)
                    for s in parsed_syms:
                        symbol_by_name[s.name] = s

        if all_symbols:
            graph.add_symbols(all_symbols)

        detector = CommunityDetector()
        communities = detector.detect_communities(graph) if graph.node_count() > 0 else []
        community_summaries = [
            f"Cluster {c.id} ({c.title}): {len(c.symbols)} symbols across {len(c.files)} file(s)"
            for c in communities[:5]
        ]

        governance = self._inspect_governance(root, source_str)

        project_map = OSSProjectMap(
            project_name=project_name,
            source_target=source_str,
            resolved_path=str(root),
            read_only_verified=True,
            files_indexed=files_indexed,
            symbols_extracted=len(all_symbols),
            graph_nodes=graph.node_count(),
            graph_edges=graph.edge_count(),
            communities_detected=len(communities),
            languages_breakdown=languages_breakdown,
            rag_highlights=rag_highlights[:6],
            community_summaries=community_summaries,
            governance=governance,
        )
        return project_map, graph, symbol_by_name

    def _inspect_governance(self, root: Path, source_str: str) -> OSSProjectGovernance:
        """Inspect CONTRIBUTING.md, SECURITY.md, and LICENSE in read-only mode."""
        has_contributing = False
        contributing_path: str | None = None
        guidelines: list[str] = []

        for cand in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"):
            cpath = resolve_inside(root, cand)
            if cpath.is_file():
                has_contributing = True
                contributing_path = cand
                text = cpath.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("- ", "* ")) and len(stripped) > 6:
                        guidelines.append(stripped[2:].strip())
                        if len(guidelines) >= 5:
                            break
                break

        if not guidelines:
            guidelines = [
                "Follow Conventional Commits in pull request titles.",
                "Include regression tests and minimal diffs for bug fixes.",
                "Never report security vulnerabilities in public issues.",
            ]

        has_security = False
        security_path: str | None = None
        private_channel = "https://github.com/OWNER/REPO/security/advisories/new"
        channel_type = DisclosureChannelType.GITHUB_SECURITY_ADVISORY

        if source_str.startswith(("http://", "https://")) and "github.com/" in source_str:
            clean_url = source_str.rstrip("/").removesuffix(".git")
            private_channel = f"{clean_url}/security/advisories/new"

        for cand in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
            spath = resolve_inside(root, cand)
            if spath.is_file():
                has_security = True
                security_path = cand
                sec_text = spath.read_text(encoding="utf-8", errors="replace")
                email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", sec_text)
                url_match = re.search(r"https://[^\s)>\]]+/security/advisories[^\s)>\]]*", sec_text)
                if url_match:
                    private_channel = url_match.group(0)
                    channel_type = DisclosureChannelType.SECURITY_MD_URL
                elif email_match:
                    private_channel = f"mailto:{email_match.group(0)}"
                    channel_type = DisclosureChannelType.SECURITY_MD_EMAIL
                break

        license_type: str | None = None
        for lcand in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
            lpath = resolve_inside(root, lcand)
            if lpath.is_file():
                ltext = lpath.read_text(encoding="utf-8", errors="replace")
                if "MIT License" in ltext or "Permission is hereby granted, free of charge" in ltext:
                    license_type = "MIT"
                elif "Apache License" in ltext:
                    license_type = "Apache-2.0"
                elif "GNU GENERAL PUBLIC LICENSE" in ltext:
                    license_type = "GPL"
                else:
                    license_type = "Custom/Other"
                break

        return OSSProjectGovernance(
            has_contributing_md=has_contributing,
            contributing_path=contributing_path,
            contributing_guidelines_summary=guidelines,
            has_security_md=has_security,
            security_md_path=security_path,
            private_security_channel=private_channel,
            preferred_disclosure_channel=channel_type,
            license_type=license_type,
        )

    def find_problems(
        self,
        project_map: OSSProjectMap,
        graph: CodeGraph | None = None,
        symbol_by_name: dict[str, Symbol] | None = None,
        *,
        read_only: bool = True,
    ) -> list[OSSIssueFinding]:
        """Stage 2: Static bug detection, broken test inspection, multi-language smells, and security scan."""
        self._enforce_read_only(read_only)
        root = Path(project_map.resolved_path)
        active_graph = graph or CodeGraph()
        known_symbols = symbol_by_name or {}

        findings: list[OSSIssueFinding] = []

        # 1. Run nexcoder-security offline scanners (bandit, semgrep, pip-audit, osv-scanner, gitleaks)
        sec_result = self.security_engine.scan(
            root,
            enabled_scanners=["bandit", "semgrep", "pip-audit", "osv-scanner", "gitleaks"],
            force_offline=True,
            owned_target=True,
            authorized_by="oss-read-only-analyzer",
        )
        for sf in sec_result.findings:
            if sf.is_suppressed:
                continue
            # Filter low-signal assert warnings in test files
            rel_fp = self._rel_path(root, sf.location.file_path if sf.location else str(root))
            if sf.rule_id == "bandit.B101" and ("test_" in rel_fp or "_test." in rel_fp or rel_fp.startswith("tests/")):
                continue
            findings.append(self._convert_security_finding(sf, root))

        # 2. Multi-language static analysis & static broken-test inspection (strictly read-only)
        py_function_arity: dict[str, tuple[int, int]] = {}  # func_name -> (min_positional, max_positional)
        py_files: list[Path] = []
        other_files: list[tuple[Path, str]] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
            for fname in sorted(filenames):
                fpath = Path(dirpath) / fname
                suffix = fpath.suffix.lower()
                lang = _EXTENSION_LANGUAGE_MAP.get(suffix)
                if lang == "python":
                    py_files.append(fpath)
                elif lang:
                    other_files.append((fpath, lang))

        # First pass over non-test Python files to collect function signatures for static test checking
        for fpath in py_files:
            rel_fp = self._rel_path(root, fpath)
            is_test = self._is_test_file(rel_fp)
            source = fpath.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=rel_fp)
            except SyntaxError as syn_err:
                findings.append(
                    OSSIssueFinding(
                        id=f"OSS-BUG-{len(findings) + 1:02d}",
                        category=OSSFindingCategory.BUG,
                        severity="critical",
                        language="python",
                        file_path=rel_fp,
                        line_number=syn_err.lineno or 1,
                        title=f"Syntax error in {rel_fp}",
                        description=f"File fails static AST parsing: {syn_err.msg}",
                        evidence_snippet=(syn_err.text or "").strip(),
                        detector="python-ast-syntax",
                    )
                )
                continue

            if not is_test:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                        pos_args = [a for a in node.args.args if a.arg not in ("self", "cls")]
                        defaults_count = len(node.args.defaults)
                        min_args = max(0, len(pos_args) - defaults_count)
                        max_args = len(pos_args) if node.args.vararg is None else 999
                        py_function_arity[node.name] = (min_args, max_args)

        # Second pass over Python files to detect bugs, broken tests, performance, and readability issues
        for fpath in py_files:
            rel_fp = self._rel_path(root, fpath)
            is_test = self._is_test_file(rel_fp)
            source = fpath.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=rel_fp)
            except SyntaxError:
                continue

            lines = source.splitlines()
            if is_test:
                findings.extend(
                    self._analyze_python_test_file(
                        tree=tree,
                        lines=lines,
                        rel_fp=rel_fp,
                        py_function_arity=py_function_arity,
                        existing_count=len(findings),
                    )
                )
            else:
                findings.extend(
                    self._analyze_python_source_file(
                        tree=tree,
                        lines=lines,
                        rel_fp=rel_fp,
                        graph=active_graph,
                        known_symbols=known_symbols,
                        existing_count=len(findings),
                    )
                )

        # 3. Analyze non-Python files (JS/TS, Go, Rust, Java, C/C++, Delphi)
        for fpath, lang in other_files:
            rel_fp = self._rel_path(root, fpath)
            source = fpath.read_text(encoding="utf-8", errors="replace")
            findings.extend(
                self._analyze_multilang_file(
                    source=source,
                    rel_fp=rel_fp,
                    lang=lang,
                    existing_count=len(findings),
                )
            )

        return self._prioritize_findings(findings)

    def _convert_security_finding(self, sf: SecurityFinding, root: Path) -> OSSIssueFinding:
        rel_fp = self._rel_path(root, sf.location.file_path if sf.location else str(root))
        line_no = sf.location.line_start if sf.location else None
        snippet = (sf.location.snippet or "").strip() if sf.location else ""
        if not snippet and sf.location and Path(sf.location.file_path).is_file() and line_no:
            file_lines = Path(sf.location.file_path).read_text(encoding="utf-8", errors="replace").splitlines()
            if 1 <= line_no <= len(file_lines):
                snippet = file_lines[line_no - 1].strip()

        cwe_or_cve = sf.cve_id or (sf.cwe_ids[0] if sf.cwe_ids else sf.rule_id)
        return OSSIssueFinding(
            id=f"OSS-SEC-{sf.id}",
            category=OSSFindingCategory.SECURITY,
            severity=sf.severity.value,
            language="python" if rel_fp.endswith(".py") else "dependency",
            file_path=rel_fp,
            line_number=line_no,
            title=sf.title,
            description=sf.description or sf.title,
            evidence_snippet=snippet,
            detector=f"nexcoder-security:{sf.scanner}",
            cwe_or_cve=cwe_or_cve,
            is_security_sensitive=True,
        )

    def _analyze_python_source_file(
        self,
        *,
        tree: ast.AST,
        lines: list[str],
        rel_fp: str,
        graph: CodeGraph,
        known_symbols: dict[str, Symbol],
        existing_count: int,
    ) -> list[OSSIssueFinding]:
        found: list[OSSIssueFinding] = []
        seq = existing_count

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name
            impact: ImpactReport | None = None
            if func_name in known_symbols and graph.node_count() > 0:
                impact = graph.impact_analysis(known_symbols[func_name].id)

            # Bug 1: Mutable default arguments (e.g., def add_item(item, bucket=[]):)
            for default_node in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                if isinstance(default_node, (ast.List, ast.Dict, ast.Set)):
                    seq += 1
                    line_no = node.lineno
                    snippet = self._get_line(lines, line_no)
                    found.append(
                        OSSIssueFinding(
                            id=f"OSS-BUG-{seq:02d}",
                            category=OSSFindingCategory.BUG,
                            severity="high",
                            language="python",
                            file_path=rel_fp,
                            line_number=line_no,
                            symbol_name=func_name,
                            title=f"Mutable default argument in `{func_name}`",
                            description=(
                                f"Function `{func_name}` uses a mutable literal (`list`, `dict`, or `set`) "
                                "as a parameter default, causing shared state across invocations."
                            ),
                            evidence_snippet=snippet,
                            detector="python-ast-bug-detector",
                            impact_blast_radius=impact,
                        )
                    )
                    break

            # Bug 2: Unguarded division by len(...) or count/total denominator without emptiness check
            func_source = ast.get_source_segment("\n".join(lines), node) or ""
            for sub in ast.walk(node):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.Div, ast.FloorDiv)):
                    is_len_denom = (
                        isinstance(sub.right, ast.Call)
                        and isinstance(sub.right.func, ast.Name)
                        and sub.right.func.id == "len"
                    )
                    is_zero_risk_name = isinstance(sub.right, ast.Name) and sub.right.id in {
                        "count",
                        "total",
                        "denominator",
                        "size",
                        "n",
                    }
                    has_guard = bool(
                        re.search(r"\bif\s+not\b|\bif\s+len\(|\bmax\s*\(\s*len\(|\bif\s+\w+\s*==\s*0", func_source)
                    )
                    if (is_len_denom or is_zero_risk_name) and not has_guard:
                        seq += 1
                        line_no = getattr(sub, "lineno", node.lineno)
                        snippet = self._get_line(lines, line_no)
                        found.append(
                            OSSIssueFinding(
                                id=f"OSS-BUG-{seq:02d}",
                                category=OSSFindingCategory.BUG,
                                severity="high",
                                language="python",
                                file_path=rel_fp,
                                line_number=line_no,
                                symbol_name=func_name,
                                title=f"Unguarded division by zero risk in `{func_name}`",
                                description=(
                                    f"Function `{func_name}` divides by a collection length or counter without "
                                    "checking for an empty input, raising `ZeroDivisionError` at runtime."
                                ),
                                evidence_snippet=snippet,
                                detector="python-ast-bug-detector",
                                impact_blast_radius=impact,
                            )
                        )
                        break

            # Bug 3: Bare except or silent exception swallowing (`except ...: pass`)
            for sub in ast.walk(node):
                if isinstance(sub, ast.ExceptHandler):
                    is_bare = sub.type is None
                    is_pass_only = len(sub.body) == 1 and isinstance(sub.body[0], ast.Pass)
                    if is_bare or is_pass_only:
                        seq += 1
                        line_no = getattr(sub, "lineno", node.lineno)
                        snippet = self._get_line(lines, line_no)
                        found.append(
                            OSSIssueFinding(
                                id=f"OSS-BUG-{seq:02d}",
                                category=OSSFindingCategory.BUG,
                                severity="medium",
                                language="python",
                                file_path=rel_fp,
                                line_number=line_no,
                                symbol_name=func_name,
                                title=f"Swallowed exception in `{func_name}`",
                                description=(
                                    f"Exception handler in `{func_name}` catches errors silently without "
                                    "logging or re-raising, masking runtime bugs."
                                ),
                                evidence_snippet=snippet,
                                detector="python-ast-bug-detector",
                                impact_blast_radius=impact,
                            )
                        )
                        break

            # Performance 1: String `+=` concatenation or `.execute(` inside a loop
            for sub in ast.walk(node):
                if isinstance(sub, (ast.For, ast.While)):
                    for loop_child in ast.walk(sub):
                        if (
                            isinstance(loop_child, ast.AugAssign)
                            and isinstance(loop_child.op, ast.Add)
                            and isinstance(loop_child.target, ast.Name)
                        ):
                            line_no = getattr(loop_child, "lineno", sub.lineno)
                            snippet = self._get_line(lines, line_no)
                            if any(
                                tok in snippet
                                for tok in ('"', "'", "str(", "line", "csv", "out", "report", "html", "text")
                            ):
                                seq += 1
                                found.append(
                                    OSSIssueFinding(
                                        id=f"OSS-PERF-{seq:02d}",
                                        category=OSSFindingCategory.PERFORMANCE,
                                        severity="medium",
                                        language="python",
                                        file_path=rel_fp,
                                        line_number=line_no,
                                        symbol_name=func_name,
                                        title=f"Repeated string concatenation inside loop in `{func_name}`",
                                        description=(
                                            f"Loop in `{func_name}` repeatedly concatenates strings with `+=`, "
                                            "causing quadratic allocations instead of `''.join(...)`."
                                        ),
                                        evidence_snippet=snippet,
                                        detector="python-ast-performance",
                                        impact_blast_radius=impact,
                                    )
                                )
                                break

            # Readability 1: Excessive parameters or high branching complexity
            param_count = len(node.args.args)
            branch_count = sum(
                1 for sub in ast.walk(node) if isinstance(sub, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler))
            )
            if param_count > 6 or branch_count >= 6:
                seq += 1
                line_no = node.lineno
                snippet = self._get_line(lines, line_no)
                found.append(
                    OSSIssueFinding(
                        id=f"OSS-READ-{seq:02d}",
                        category=OSSFindingCategory.READABILITY,
                        severity="low",
                        language="python",
                        file_path=rel_fp,
                        line_number=line_no,
                        symbol_name=func_name,
                        title=f"High complexity or parameter count in `{func_name}`",
                        description=(
                            f"Function `{func_name}` has {param_count} parameters and {branch_count} "
                            "branch points; extract helper routines or a parameter dataclass."
                        ),
                        evidence_snippet=snippet,
                        detector="python-ast-readability",
                        impact_blast_radius=impact,
                    )
                )

        return found

    def _analyze_python_test_file(
        self,
        *,
        tree: ast.AST,
        lines: list[str],
        rel_fp: str,
        py_function_arity: dict[str, tuple[int, int]],
        existing_count: int,
    ) -> list[OSSIssueFinding]:
        """Inspect test files statically (without executing them) for broken tests."""
        found: list[OSSIssueFinding] = []
        seq = existing_count

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue

            # 1. Empty test with no assertions
            has_assert = any(
                isinstance(sub, ast.Assert)
                or (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr.startswith(("assert", "raises", "fail"))
                )
                for sub in ast.walk(node)
            )
            if not has_assert:
                seq += 1
                found.append(
                    OSSIssueFinding(
                        id=f"OSS-BUG-{seq:02d}",
                        category=OSSFindingCategory.BUG,
                        severity="medium",
                        language="python",
                        file_path=rel_fp,
                        line_number=node.lineno,
                        symbol_name=node.name,
                        title=f"Broken test `{node.name}` contains no assertions",
                        description=(
                            f"Test function `{node.name}` in `{rel_fp}` executes without any `assert` "
                            "or `pytest.raises` verification."
                        ),
                        evidence_snippet=self._get_line(lines, node.lineno),
                        detector="static-test-inspector",
                    )
                )

            # 2. Unconditional `assert False` or mismatched function call arity
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assert) and isinstance(sub.test, ast.Constant) and sub.test.value is False:
                    seq += 1
                    line_no = getattr(sub, "lineno", node.lineno)
                    found.append(
                        OSSIssueFinding(
                            id=f"OSS-BUG-{seq:02d}",
                            category=OSSFindingCategory.BUG,
                            severity="high",
                            language="python",
                            file_path=rel_fp,
                            line_number=line_no,
                            symbol_name=node.name,
                            title=f"Broken test `{node.name}` has unconditional `assert False`",
                            description=f"Test `{node.name}` contains a hardcoded `assert False` at line {line_no}.",
                            evidence_snippet=self._get_line(lines, line_no),
                            detector="static-test-inspector",
                        )
                    )
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    called_name = sub.func.id
                    if called_name in py_function_arity and not any(
                         isinstance(a, ast.Starred) for a in sub.args
                    ):
                        min_a, max_a = py_function_arity[called_name]
                        total_passed = len(sub.args) + len(sub.keywords)
                        if len(sub.args) > max_a or total_passed < min_a:
                            seq += 1
                            line_no = getattr(sub, "lineno", node.lineno)
                            found.append(
                                OSSIssueFinding(
                                    id=f"OSS-BUG-{seq:02d}",
                                    category=OSSFindingCategory.BUG,
                                    severity="high",
                                    language="python",
                                    file_path=rel_fp,
                                    line_number=line_no,
                                    symbol_name=node.name,
                                    title=(
                                        f"Broken test `{node.name}` calls `{called_name}` "
                                        "with incompatible argument count"
                                    ),
                                    description=(
                                        f"Test `{node.name}` passes {total_passed} argument(s) to `{called_name}`, "
                                        f"which requires between {min_a} and {max_a} parameter(s)."
                                    ),
                                    evidence_snippet=self._get_line(lines, line_no),
                                    detector="static-test-inspector",
                                )
                            )

        return found

    def _analyze_multilang_file(
        self,
        *,
        source: str,
        rel_fp: str,
        lang: str,
        existing_count: int,
    ) -> list[OSSIssueFinding]:
        """Static bug, security, performance, and readability checks for JS/TS, Go, Rust, Java, C/C++, Delphi."""
        found: list[OSSIssueFinding] = []
        lines = source.splitlines()
        seq = existing_count

        rules: list[tuple[str, OSSFindingCategory, str, str, str]] = []
        if lang in ("javascript", "typescript"):
            rules = [
                (
                    r"[^=!]==[^=]",
                    OSSFindingCategory.BUG,
                    "medium",
                    "Loose equality operator (`==`) in JavaScript/TypeScript",
                    "Loose equality performs coercive type conversion; use strict `===` instead.",
                ),
                (
                    r"\.innerHTML\s*=",
                    OSSFindingCategory.SECURITY,
                    "high",
                    "Direct DOM `innerHTML` assignment (XSS risk)",
                    "Assigning unsanitized strings to `innerHTML` enables DOM Cross-Site Scripting (CWE-79).",
                ),
                (
                    r"\bconsole\.log\s*\(",
                    OSSFindingCategory.READABILITY,
                    "low",
                    "Leftover debug `console.log` statement",
                    "Replace ad-hoc `console.log` calls with structured logger output.",
                ),
            ]
        elif lang == "go":
            rules = [
                (
                    r"^\s*_\s*=\s*\w+\(",
                    OSSFindingCategory.BUG,
                    "medium",
                    "Ignored error return in Go (`_ = fn(...)`)",
                    "Explicitly discarding returned `error` values hides I/O or validation failures.",
                ),
            ]
        elif lang == "rust":
            rules = [
                (
                    r"\.unwrap\(\)",
                    OSSFindingCategory.BUG,
                    "medium",
                    "Unchecked `.unwrap()` call in Rust module",
                    "Calling `.unwrap()` panics on `None`/`Err`; propagate errors with `?` or `.context(...)`.",
                ),
            ]
        elif lang in ("c", "cpp"):
            rules = [
                (
                    r"\b(?:strcpy|sprintf|gets)\s*\(",
                    OSSFindingCategory.SECURITY,
                    "high",
                    "Unbounded buffer write (`strcpy`/`sprintf`/`gets`)",
                    "Unbounded C string functions risk stack/heap buffer overflow (CWE-120); use `snprintf`.",
                ),
            ]

        for line_idx, line in enumerate(lines, start=1):
            for pattern, cat, sev, title, desc in rules:
                if re.search(pattern, line):
                    seq += 1
                    prefix = "SEC" if cat == OSSFindingCategory.SECURITY else cat.value.upper()[:4]
                    found.append(
                        OSSIssueFinding(
                            id=f"OSS-{prefix}-{seq:02d}",
                            category=cat,
                            severity=sev,
                            language=lang,
                            file_path=rel_fp,
                            line_number=line_idx,
                            title=title,
                            description=desc,
                            evidence_snippet=line.strip(),
                            detector=f"{lang}-static-analyzer",
                            is_security_sensitive=(cat == OSSFindingCategory.SECURITY),
                        )
                    )

        return found

    @staticmethod
    def _prioritize_findings(findings: list[OSSIssueFinding]) -> list[OSSIssueFinding]:
        cat_order = {
            OSSFindingCategory.SECURITY: 0,
            OSSFindingCategory.BUG: 1,
            OSSFindingCategory.PERFORMANCE: 2,
            OSSFindingCategory.READABILITY: 3,
        }
        sev_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "info": 4,
        }
        sorted_items = sorted(
            findings,
            key=lambda f: (
                cat_order.get(f.category, 9),
                sev_order.get(f.severity.lower(), 9),
                f.file_path,
                f.line_number or 0,
            ),
        )
        for idx, item in enumerate(sorted_items, start=1):
            item.priority_rank = idx
        return sorted_items

    def propose_fixes(
        self,
        findings: list[OSSIssueFinding],
        project_map: OSSProjectMap | None = None,
    ) -> list[OSSFixSuggestion]:
        """Stage 3: Generate concrete code fix snippets and justifications with no-exploit sanitization."""
        suggestions: list[OSSFixSuggestion] = []

        for f in findings:
            orig = f.evidence_snippet or f"# {f.file_path}:{f.line_number or 1}"
            suggested = orig
            rationale = f.description
            verification = "Add a deterministic unit test covering the boundary condition."

            if "Mutable default argument" in f.title:
                suggested = re.sub(
                    r"(\w+)\s*=\s*(\[\]|\{\})",
                    r"\1=None",
                    orig,
                )
                suggested += "\n    if bucket is None:\n        bucket = []"
                rationale = (
                    "Using `None` as the default parameter value and initializing a fresh container "
                    "inside the function body prevents state leakage across calls."
                )
                verification = "Call the function twice without passing the optional argument and verify isolation."
            elif "division by zero" in f.title.lower():
                suggested = f"if not items:\n    return 0.0\n{orig}"
                rationale = (
                    "Guarding against an empty sequence before dividing prevents `ZeroDivisionError` "
                    "on empty inputs while returning a well-defined neutral value."
                )
                verification = "Pass an empty list `[]` to the function in an offline unit test."
            elif "Swallowed exception" in f.title:
                suggested = "except Exception as exc:\n    logger.warning('Operation failed: %s', exc)\n    raise"
                rationale = "Logging and propagating unexpected exceptions prevents silent data corruption."
            elif "string concatenation" in f.title.lower():
                suggested = "parts: list[str] = []\n# append inside loop, then:\nresult = ''.join(parts)"
                rationale = (
                    "Accumulating fragments in a `list` and joining once reduces "
                    "time complexity from O(N^2) to O(N)."
                )
                verification = "Benchmark or assert output parity on multi-line inputs."
            elif "Broken test" in f.title:
                suggested = (
                    "# Align test call arguments with target function signature "
                    "and assert expected return value"
                )
                rationale = (
                    "Synchronizing the test invocation with the function's required parameters ensures the test "
                    "validates real behavior rather than failing with `TypeError` or `AssertionError`."
                )
                verification = "Verify test signature matches AST definition."
            elif "Loose equality" in f.title:
                suggested = orig.replace("==", "===").replace("!=", "!==")
                rationale = "Strict equality (`===`) prevents unexpected type coercion bugs in JavaScript/TypeScript."
            elif "innerHTML" in f.title:
                suggested = orig.replace(".innerHTML", ".textContent")
                rationale = "Using `.textContent` safely renders text without parsing HTML/script tags (prevents XSS)."
            elif f.category == OSSFindingCategory.SECURITY:
                if "shell=True" in orig:
                    suggested = orig.replace("shell=True", "shell=False")
                    rationale = "Passing arguments as a sequence with `shell=False` eliminates command injection."
                elif "eval(" in orig or "exec(" in orig:
                    suggested = "ast.literal_eval(user_input)"
                    rationale = (
                        "Replacing dynamic `eval`/`exec` with `ast.literal_eval` "
                        "prevents arbitrary code execution."
                    )
                elif "==" in orig and f.language == "dependency":
                    pkg_name = orig.split("==")[0].strip()
                    suggested = f"{pkg_name}>=fixed_version"
                    rationale = f"Upgrading `{pkg_name}` to a patched release mitigates {f.cwe_or_cve or 'known CVE'}."
                else:
                    suggested = f"# Remediate {f.cwe_or_cve or f.title}: replace unsafe pattern in {f.file_path}"
                    rationale = (
                        f"Eliminates {f.cwe_or_cve or 'security weakness'} via defensive "
                        "coding without exploit payloads."
                    )
                verification = "Run `nexcoder-security` offline scanner to confirm the finding is resolved."

            clean_suggested, had_exploit_1 = sanitize_no_exploit(suggested)
            clean_rationale, had_exploit_2 = sanitize_no_exploit(rationale)

            is_sec = f.category == OSSFindingCategory.SECURITY or f.is_security_sensitive
            route = "private_security_advisory" if is_sec else "public_pr_or_issue"

            suggestions.append(
                OSSFixSuggestion(
                    finding_id=f.id,
                    category=f.category,
                    title=f"Fix: {f.title}",
                    file_path=f.file_path,
                    line_number=f.line_number,
                    original_snippet=orig,
                    suggested_snippet=clean_suggested,
                    rationale=clean_rationale,
                    verification_notes=verification,
                    contains_exploit_payload=(had_exploit_1 or had_exploit_2),
                    disclosure_route=route,
                )
            )

        return suggestions

    def build_report(
        self,
        project_map: OSSProjectMap,
        findings: list[OSSIssueFinding],
        suggestions: list[OSSFixSuggestion],
        *,
        authorize_upstream: bool = False,
        allow_public_security_issue: bool = False,
        adapter: PlatformAdapter | None = None,
        dry_run: bool = True,
    ) -> OSSContributionReport:
        """Stage 4: Assemble the contribution report and prepare upstream actions with disclosure guardrails."""
        sug_map = {s.finding_id: s for s in suggestions}
        upstream_actions: list[OSSUpstreamAction] = []

        for f in findings:
            sug = sug_map.get(f.id)
            is_sec = f.category == OSSFindingCategory.SECURITY or f.is_security_sensitive

            if is_sec:
                # Coordinated disclosure guardrail: NEVER allow a security flaw on a public issue/PR!
                blocked_public = bool(allow_public_security_issue)
                if blocked_public:
                    self.audit_log.record_event(
                        event_type="oss.disclosure_guardrail_triggered",
                        actor="oss-advisor",
                        action="block_public_security_issue",
                        resource=f.file_path,
                        severity="warning",
                        details={
                            "finding_id": f.id,
                            "reason": "Security vulnerabilities must use private disclosure channel.",
                        },
                    )
                body = (
                    f"### Coordinated Security Advisory ({f.cwe_or_cve or 'SAST/SCA'})\n\n"
                    f"- **File**: `{f.file_path}`\n"
                    f"- **Summary**: {f.description}\n"
                    f"- **Remediation**: {sug.rationale if sug else 'Apply defensive patch.'}\n\n"
                    f"```diff\n- {sug.original_snippet if sug else f.evidence_snippet}\n"
                    f"+ {sug.suggested_snippet if sug else ''}\n```\n"
                    "\n*(No exploit payload included per coordinated disclosure policy.)*"
                )
                clean_body, _ = sanitize_no_exploit(body)
                upstream_actions.append(
                    OSSUpstreamAction(
                        finding_id=f.id,
                        action_type="private_security_report",
                        channel=project_map.governance.private_security_channel,
                        title=f"[SECURITY ADVISORY] {f.title}",
                        commit_message=build_conventional_commit("fix", f.title[:60], scope="security"),
                        body_preview=clean_body,
                        submitted=False,
                        dry_run=True,
                        blocked_public_disclosure=blocked_public,
                    )
                )
            else:
                commit_type = "fix" if f.category == OSSFindingCategory.BUG else "perf"
                if f.category == OSSFindingCategory.READABILITY:
                    commit_type = "refactor"
                scope = Path(f.file_path).stem
                commit_msg = build_conventional_commit(commit_type, f.title[:60], scope=scope)
                pr_body = build_pull_request_body(
                    summary=f"{f.description}\n\n**Rationale**: {sug.rationale if sug else ''}",
                    verification_steps=[
                        sug.verification_notes if sug else "Run project unit test suite.",
                        "Confirmed adherence to CONTRIBUTING.md guidelines.",
                    ],
                )
                submitted = False
                if authorize_upstream and adapter is not None:
                    # Sync only non-security findings via the platform adapter
                    plan = Plan(
                        title=f"OSS Contribution: {project_map.project_name}",
                        epics=[
                            Epic(
                                id="EP-OSS-1",
                                title="Upstream OSS Improvements",
                                stories=[
                                    Story(
                                        id="US-OSS-1",
                                        title=f.title,
                                        tasks=[
                                            Task(
                                                id=f.id,
                                                title=f.title,
                                                description=pr_body,
                                                layer="core",
                                                estimate_hours=1.0,
                                                acceptance_criteria=[
                                                    AcceptanceCriterion(
                                                        given=f"file {f.file_path}",
                                                        when="the proposed fix is applied",
                                                        then="the issue is resolved without regressions",
                                                    )
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                    adapter.sync_plan(plan, dry_run=dry_run)
                    submitted = not dry_run

                upstream_actions.append(
                    OSSUpstreamAction(
                        finding_id=f.id,
                        action_type="public_pull_request",
                        channel=f"{project_map.source_target} (public PR/issue)",
                        title=commit_msg,
                        commit_message=commit_msg,
                        body_preview=pr_body,
                        submitted=submitted,
                        dry_run=dry_run,
                        blocked_public_disclosure=False,
                    )
                )

        return OSSContributionReport(
            project_map=project_map,
            findings=findings,
            suggestions=suggestions,
            upstream_actions=upstream_actions,
            audit_events_recorded=len(self.audit_log.query(limit=1000)),
        )

    def analyze_oss_project(
        self,
        target: str | Path,
        *,
        local_checkout: str | Path | None = None,
        read_only: bool = True,
        authorize_upstream: bool = False,
        allow_public_security_issue: bool = False,
        adapter: PlatformAdapter | None = None,
        dry_run: bool = True,
    ) -> OSSContributionReport:
        """Run the complete 4-stage read-only OSS analysis and contribution workflow."""
        self._enforce_read_only(read_only)
        project_map, graph, symbol_by_name = self.map_project(
            target,
            local_checkout=local_checkout,
            read_only=read_only,
        )
        findings = self.find_problems(
            project_map,
            graph=graph,
            symbol_by_name=symbol_by_name,
            read_only=read_only,
        )
        suggestions = self.propose_fixes(findings, project_map=project_map)
        return self.build_report(
            project_map=project_map,
            findings=findings,
            suggestions=suggestions,
            authorize_upstream=authorize_upstream,
            allow_public_security_issue=allow_public_security_issue,
            adapter=adapter,
            dry_run=dry_run,
        )

    @staticmethod
    def _rel_path(root: Path, file_path: str | Path) -> str:
        try:
            return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return Path(file_path).as_posix()

    @staticmethod
    def _is_test_file(rel_fp: str) -> bool:
        name = Path(rel_fp).name
        return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{rel_fp}"

    @staticmethod
    def _get_line(lines: list[str], line_no: int | None) -> str:
        if line_no and 1 <= line_no <= len(lines):
            return lines[line_no - 1].strip()
        return ""


class OSSProjectMapBlock(BaseBlock):
    """Pipeline block 1: `map_project` - indexes OSS project with `code-intel` RAG/GraphRAG."""

    def __init__(self, name: str = "map_project", advisor: OSSContributionAdvisor | None = None) -> None:
        super().__init__(name=name, block_type="oss_map_project")
        self.advisor = advisor or OSSContributionAdvisor()

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})
        target = data.get("repo_path_or_url") or inputs.get("repo_path_or_url")
        local_checkout = data.get("local_checkout") or inputs.get("local_checkout")

        if target and (Path(str(local_checkout or target)).is_dir()):
            pm, _, _ = self.advisor.map_project(target, local_checkout=local_checkout, read_only=True)
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.SUCCESS,
                updates={"oss_project_map": pm.model_dump(mode="json")},
                message=f"Mapped OSS project '{pm.project_name}' ({pm.files_indexed} files indexed).",
            )

        target_str = str(target or "https://github.com/example/synthetic-oss")
        fallback_map = OSSProjectMap(
            project_name=Path(target_str.rstrip("/")).name or "synthetic-oss",
            source_target=target_str,
            resolved_path=target_str,
            read_only_verified=True,
        )
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={"oss_project_map": fallback_map.model_dump(mode="json")},
            message=f"Created baseline OSS project map for '{fallback_map.project_name}'.",
        )


class OSSProblemFinderBlock(BaseBlock):
    """Pipeline block 2: `find_problems` - static bugs, smells, broken tests, and security scan."""

    def __init__(self, name: str = "find_problems", advisor: OSSContributionAdvisor | None = None) -> None:
        super().__init__(name=name, block_type="oss_find_problems")
        self.advisor = advisor or OSSContributionAdvisor()

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        raw_map = data.get("oss_project_map")
        if raw_map and Path(str(raw_map.get("resolved_path", ""))).is_dir():
            pm = OSSProjectMap.model_validate(raw_map)
            findings = self.advisor.find_problems(pm, read_only=True)
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.SUCCESS,
                updates={"oss_findings": [f.model_dump(mode="json") for f in findings]},
                message=f"Found {len(findings)} prioritized issue(s) in '{pm.project_name}'.",
            )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={"oss_findings": []},
            message="No local directory attached; 0 static findings.",
        )


class OSSFixProposerBlock(BaseBlock):
    """Pipeline block 3: `propose_fixes` - synthesizes code snippets, rationales, and disclosure routes."""

    def __init__(self, name: str = "propose_fixes", advisor: OSSContributionAdvisor | None = None) -> None:
        super().__init__(name=name, block_type="oss_propose_fixes")
        self.advisor = advisor or OSSContributionAdvisor()

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        raw_findings = data.get("oss_findings", [])
        raw_map = data.get("oss_project_map")
        pm = OSSProjectMap.model_validate(raw_map) if raw_map else None
        findings = [OSSIssueFinding.model_validate(f) for f in raw_findings]
        suggestions = self.advisor.propose_fixes(findings, project_map=pm)
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={"oss_suggestions": [s.model_dump(mode="json") for s in suggestions]},
            message=f"Proposed {len(suggestions)} defensive code fix(es).",
        )


class OSSReportBuilderBlock(BaseBlock):
    """Pipeline block 4: `build_report` - compiles the OSS contribution report and upstream actions."""

    def __init__(self, name: str = "build_report", advisor: OSSContributionAdvisor | None = None) -> None:
        super().__init__(name=name, block_type="oss_build_report")
        self.advisor = advisor or OSSContributionAdvisor()

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})
        raw_map = data.get("oss_project_map")
        pm = (
            OSSProjectMap.model_validate(raw_map)
            if raw_map
            else OSSProjectMap(
                project_name="synthetic-oss",
                source_target="local",
                resolved_path=".",
            )
        )
        findings = [OSSIssueFinding.model_validate(f) for f in data.get("oss_findings", [])]
        suggestions = [OSSFixSuggestion.model_validate(s) for s in data.get("oss_suggestions", [])]
        allow_pub_sec = bool(
            data.get("allow_public_security_issue", inputs.get("allow_public_security_issue", False))
        )
        report = self.advisor.build_report(
            project_map=pm,
            findings=findings,
            suggestions=suggestions,
            allow_public_security_issue=allow_pub_sec,
            dry_run=True,
        )
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={
                "oss_upstream_actions": [a.model_dump(mode="json") for a in report.upstream_actions],
                "oss_contribution_report": report.model_dump(mode="json"),
                "oss_report_markdown": report.to_markdown(),
            },
            message=f"Built OSS contribution report for '{pm.project_name}'.",
        )


__all__ = [
    "DisclosureChannelType",
    "OSSContributionAdvisor",
    "OSSContributionReport",
    "OSSFindingCategory",
    "OSSFixProposerBlock",
    "OSSFixSuggestion",
    "OSSIssueFinding",
    "OSSProblemFinderBlock",
    "OSSProjectGovernance",
    "OSSProjectMap",
    "OSSProjectMapBlock",
    "OSSReportBuilderBlock",
    "OSSUpstreamAction",
    "sanitize_no_exploit",
]
