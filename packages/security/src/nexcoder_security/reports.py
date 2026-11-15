"""Security posture metrics extractor and NexDash dashboard builder for nexcoder-security.

Transforms multi-scanner ``ScanResult`` findings, ``SBOMDocument`` components, and
``GateVerdict`` evaluations into the ``security_posture`` semantic cube and
requests rendered dashboards from NexDash via MCP, REST, or offline mode.
"""

from __future__ import annotations

from typing import Any

from nexcoder_core.reports import (
    NexDashClient,
    NexDashComputedChart,
    NexDashComputedKPI,
    NexDashCubeSpec,
    NexDashDashboardBundle,
    NexDashDimensionSpec,
    NexDashMetricSpec,
    NexDashPlanFilter,
    NexDashQueryPlan,
    TransportKind,
)
from pydantic import BaseModel, Field

from nexcoder_security.gate.evaluator import SecurityGateEvaluator
from nexcoder_security.gate.policy import GatePolicy, GateVerdict
from nexcoder_security.models import (
    Finding,
    FindingCategory,
    Location,
    Remediation,
    SBOMComponent,
    SBOMDocument,
    ScanMetadata,
    ScanResult,
    Severity,
)

DEFAULT_EXPECTED_SCANNERS = [
    "semgrep",
    "bandit",
    "gitleaks",
    "osv-scanner",
    "pip-audit",
    "trivy",
    "syft",
]


class OutdatedDependencyItem(BaseModel):
    """Dependency requiring upgrade due to SCA vulnerability or version lag."""

    package_name: str
    current_version: str
    recommended_version: str
    severity: str
    cve_id: str | None = None
    rule_id: str = ""


class ScannerCoverageItem(BaseModel):
    """Execution and finding metrics for an individual scanner in the release gate."""

    scanner: str
    executed: bool
    findings_count: int = 0
    blocking_count: int = 0
    is_fallback: bool = False


class SecurityTrendPoint(BaseModel):
    """Historical point tracking vulnerabilities and gate status across periods."""

    period: str
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total_active: int = 0
    fixed_count: int = 0
    gate_passed: bool = True


class SecurityPostureMetrics(BaseModel):
    """Consolidated security posture metrics for NexDash reporting."""

    project: str
    period: str
    policy_name: str = "default-production-gate"
    total_findings: int = 0
    suppressed_findings: int = 0
    blocking_findings: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)
    scanner_counts: dict[str, int] = Field(default_factory=dict)
    gate_passed: bool = True
    gate_pass_rate_pct: float = 100.0
    gate_coverage_pct: float = 100.0
    expected_scanners: list[str] = Field(default_factory=list)
    executed_scanners: list[str] = Field(default_factory=list)
    sbom_present: bool = False
    sbom_components_count: int = 0
    outdated_dependencies_count: int = 0
    outdated_dependencies: list[OutdatedDependencyItem] = Field(default_factory=list)
    trend: list[SecurityTrendPoint] = Field(default_factory=list)
    scanner_coverage: list[ScannerCoverageItem] = Field(default_factory=list)


def build_synthetic_security_scans(
    project: str = "nexcoder-platform",
    policy: GatePolicy | None = None,
) -> list[tuple[str, ScanResult, GateVerdict]]:
    """Build deterministic multi-period security scan history for offline testing and demos."""
    evaluator = SecurityGateEvaluator(default_policy=policy or GatePolicy(require_sbom=True))
    sbom = SBOMDocument(
        format="cyclonedx",
        schema_version="1.5",
        components=[
            SBOMComponent(name="fastapi", version="0.110.0", purl="pkg:pypi/fastapi@0.110.0", licenses=["MIT"]),
            SBOMComponent(name="pydantic", version="2.7.1", purl="pkg:pypi/pydantic@2.7.1", licenses=["MIT"]),
            SBOMComponent(name="httpx", version="0.27.0", purl="pkg:pypi/httpx@0.27.0", licenses=["BSD-3-Clause"]),
            SBOMComponent(name="pyyaml", version="6.0.1", purl="pkg:pypi/pyyaml@6.0.1", licenses=["MIT"]),
            SBOMComponent(name="urllib3", version="2.0.2", purl="pkg:pypi/urllib3@2.0.2", licenses=["MIT"]),
            SBOMComponent(name="jinja2", version="3.1.2", purl="pkg:pypi/jinja2@3.1.2", licenses=["BSD-3-Clause"]),
        ],
        raw_content='{"bomFormat": "CycloneDX", "specVersion": "1.5"}',
    )

    # Week 42: 1 critical secret, 2 high SAST/SCA, 4 medium, 2 low
    w42_findings = [
        Finding(
            id="f-w42-1",
            scanner="gitleaks",
            rule_id="generic-api-key",
            title="Hardcoded API token in test fixture",
            severity=Severity.CRITICAL,
            category=FindingCategory.SECRET,
            location=Location(file_path="tests/fixtures/config.py", line_start=12),
        ),
        Finding(
            id="f-w42-2",
            scanner="semgrep",
            rule_id="python.lang.security.audit.formatted-sql-query",
            title="Unparameterized SQL string formatting",
            severity=Severity.HIGH,
            category=FindingCategory.SAST,
            cwe_ids=["CWE-89"],
            location=Location(file_path="src/db/query.py", line_start=44),
        ),
        Finding(
            id="f-w42-3",
            scanner="pip-audit",
            rule_id="PYSEC-2023-212",
            title="urllib3 request body not stripped on redirect",
            severity=Severity.HIGH,
            category=FindingCategory.SCA,
            cve_id="CVE-2023-45803",
            remediation=Remediation(summary="Upgrade urllib3", recommended_version="2.2.2"),
            raw_data={"package": "urllib3", "installed_version": "2.0.2"},
        ),
        Finding(
            id="f-w42-4",
            scanner="osv-scanner",
            rule_id="GHSA-h75v-3vvj-5mfj",
            title="jinja2 xmlattr filter attribute injection",
            severity=Severity.MEDIUM,
            category=FindingCategory.SCA,
            cve_id="CVE-2024-22195",
            remediation=Remediation(summary="Upgrade jinja2", recommended_version="3.1.4"),
            raw_data={"package": "jinja2", "installed_version": "3.1.2"},
        ),
        Finding(
            id="f-w42-5",
            scanner="bandit",
            rule_id="B113",
            title="Request call without explicit timeout",
            severity=Severity.MEDIUM,
            category=FindingCategory.SAST,
            location=Location(file_path="src/client/http.py", line_start=29),
        ),
        Finding(
            id="f-w42-6",
            scanner="trivy",
            rule_id="DS002",
            title="Container image runs as root user",
            severity=Severity.MEDIUM,
            category=FindingCategory.CONTAINER,
            location=Location(file_path="Dockerfile", line_start=8),
        ),
        Finding(
            id="f-w42-7",
            scanner="semgrep",
            rule_id="python.fastapi.security.wildcard-cors",
            title="Permissive CORS configuration review",
            severity=Severity.MEDIUM,
            category=FindingCategory.SAST,
            location=Location(file_path="src/api/app.py", line_start=19),
        ),
        Finding(
            id="f-w42-8",
            scanner="bandit",
            rule_id="B101",
            title="Use of assert detected in helper",
            severity=Severity.LOW,
            category=FindingCategory.SAST,
            location=Location(file_path="src/utils/validators.py", line_start=15),
        ),
        Finding(
            id="f-w42-9",
            scanner="trivy",
            rule_id="DS026",
            title="No HEALTHCHECK instruction in Dockerfile",
            severity=Severity.LOW,
            category=FindingCategory.IAC,
            location=Location(file_path="Dockerfile", line_start=1),
        ),
    ]

    # Week 43: Secret removed, SQL injection fixed; 1 high SCA remains, 3 medium, 2 low
    w43_findings = [
        w42_findings[2],
        w42_findings[3],
        w42_findings[4],
        w42_findings[5],
        w42_findings[7],
        w42_findings[8],
    ]

    # Week 44: High SCA fixed; 0 critical, 0 high, 3 medium, 2 low -> Gate PASSED
    w44_findings = [w42_findings[3], w42_findings[4], w42_findings[5], w42_findings[7], w42_findings[8]]

    # Week 45: Current scan -> 0 critical, 0 high, 2 medium, 1 low, 1 suppressed -> Gate PASSED
    suppressed_finding = w42_findings[7].model_copy(
        update={"is_suppressed": True, "suppression_reason": "Validated in test helper"}
    )
    w45_findings = [w42_findings[3], w42_findings[4], w42_findings[8], suppressed_finding]

    periods = [
        ("2026-W42", w42_findings),
        ("2026-W43", w43_findings),
        ("2026-W44", w44_findings),
        ("2026-W45", w45_findings),
    ]

    history: list[tuple[str, ScanResult, GateVerdict]] = []
    for period_label, findings_list in periods:
        scan_res = ScanResult(
            scanner="multi-scanner (semgrep,bandit,gitleaks,osv-scanner,pip-audit,trivy,syft)",
            target_path=project,
            findings=findings_list,
            metadata=ScanMetadata(
                scanner="multi-scanner",
                version="0.1.0",
                target_path=project,
                duration_seconds=1.4,
                timestamp=f"{period_label}",
                success=True,
                is_fallback=False,
            ),
            sbom=sbom,
        )
        verdict = evaluator.evaluate(scan_res, sbom=sbom)
        history.append((period_label, scan_res, verdict))

    return history


def _extract_executed_scanners(scan_result: ScanResult) -> set[str]:
    executed: set[str] = set()
    for f in scan_result.findings:
        if f.scanner:
            executed.add(f.scanner.strip().lower())
    if scan_result.sbom and scan_result.sbom.components:
        executed.add("syft")
    scanner_header = (scan_result.scanner or "").lower()
    for candidate in DEFAULT_EXPECTED_SCANNERS:
        if candidate in scanner_header:
            executed.add(candidate)
    if scan_result.metadata and scan_result.metadata.scanner:
        meta_scanner = scan_result.metadata.scanner.lower()
        for candidate in DEFAULT_EXPECTED_SCANNERS:
            if candidate in meta_scanner:
                executed.add(candidate)
        if meta_scanner == "multi-scanner" and not executed:
            executed.update(["semgrep", "bandit", "gitleaks", "osv-scanner", "pip-audit", "trivy", "syft"])
    return executed


def compute_security_metrics(
    scan_result: ScanResult,
    *,
    history: list[tuple[str, ScanResult, GateVerdict]] | None = None,
    policy: GatePolicy | None = None,
    project: str = "nexcoder-platform",
    period: str = "2026-Q4",
    expected_scanners: list[str] | None = None,
) -> SecurityPostureMetrics:
    """Compute security posture, severity distribution, trend, and gate coverage metrics."""
    active_policy = policy or GatePolicy()
    evaluator = SecurityGateEvaluator(default_policy=active_policy)
    verdict = evaluator.evaluate(scan_result, policy=active_policy, sbom=scan_result.sbom)

    sev_counts: dict[str, int] = {
        Severity.CRITICAL.value: 0,
        Severity.HIGH.value: 0,
        Severity.MEDIUM.value: 0,
        Severity.LOW.value: 0,
        Severity.INFO.value: 0,
    }
    cat_counts: dict[str, int] = {c.value: 0 for c in FindingCategory}
    scanner_counts: dict[str, int] = {}
    suppressed_count = 0
    outdated_deps: list[OutdatedDependencyItem] = []

    comp_versions: dict[str, str] = {}
    if scan_result.sbom:
        for comp in scan_result.sbom.components:
            comp_versions[comp.name.lower()] = comp.version

    for f in scan_result.findings:
        if f.is_suppressed:
            suppressed_count += 1
            continue
        sev_counts[f.severity.value] = sev_counts.get(f.severity.value, 0) + 1
        cat_counts[f.category.value] = cat_counts.get(f.category.value, 0) + 1
        sc_name = f.scanner.lower()
        scanner_counts[sc_name] = scanner_counts.get(sc_name, 0) + 1

        if f.remediation and f.remediation.recommended_version:
            pkg_name = str(f.raw_data.get("package") or f.title.split()[0]).lower()
            curr_ver = str(f.raw_data.get("installed_version") or comp_versions.get(pkg_name, "unknown"))
            outdated_deps.append(
                OutdatedDependencyItem(
                    package_name=pkg_name,
                    current_version=curr_ver,
                    recommended_version=f.remediation.recommended_version,
                    severity=f.severity.value,
                    cve_id=f.cve_id,
                    rule_id=f.rule_id,
                )
            )

    expected = [s.lower() for s in (expected_scanners or DEFAULT_EXPECTED_SCANNERS)]
    executed_set = _extract_executed_scanners(scan_result)
    executed_list = [s for s in expected if s in executed_set]
    coverage_pct = round((len(executed_list) / len(expected)) * 100.0, 1) if expected else 100.0

    blocking_ids = {bf.id for bf in verdict.blocking_findings}
    scanner_cov_items: list[ScannerCoverageItem] = []
    for sc in expected:
        sc_findings = [f for f in scan_result.findings if not f.is_suppressed and f.scanner.lower() == sc]
        sc_blocking = [f for f in sc_findings if f.id in blocking_ids]
        scanner_cov_items.append(
            ScannerCoverageItem(
                scanner=sc,
                executed=sc in executed_set,
                findings_count=len(sc_findings),
                blocking_count=len(sc_blocking),
                is_fallback=sc in [fb.lower() for fb in scan_result.fallbacks],
            )
        )

    trend_points: list[SecurityTrendPoint] = []
    active_history = history or [(period, scan_result, verdict)]
    prev_total: int | None = None
    passed_runs = 0

    for per_label, h_scan, h_verdict in active_history:
        if h_verdict.passed:
            passed_runs += 1
        c_cnt = len(h_scan.by_severity(Severity.CRITICAL))
        h_cnt = len(h_scan.by_severity(Severity.HIGH))
        m_cnt = len(h_scan.by_severity(Severity.MEDIUM))
        l_cnt = len(h_scan.by_severity(Severity.LOW))
        i_cnt = len(h_scan.by_severity(Severity.INFO))
        tot_active = c_cnt + h_cnt + m_cnt + l_cnt + i_cnt
        fixed = max(0, prev_total - tot_active) if prev_total is not None else 0
        prev_total = tot_active

        trend_points.append(
            SecurityTrendPoint(
                period=per_label,
                critical=c_cnt,
                high=h_cnt,
                medium=m_cnt,
                low=l_cnt,
                info=i_cnt,
                total_active=tot_active,
                fixed_count=fixed,
                gate_passed=h_verdict.passed,
            )
        )

    gate_pass_rate = round((passed_runs / len(active_history)) * 100.0, 1) if active_history else 100.0
    sbom_ok = bool(scan_result.sbom and len(scan_result.sbom.components) > 0)
    sbom_count = len(scan_result.sbom.components) if scan_result.sbom else 0

    return SecurityPostureMetrics(
        project=project,
        period=period,
        policy_name=verdict.policy_name,
        total_findings=scan_result.total_findings(include_suppressed=False),
        suppressed_findings=suppressed_count,
        blocking_findings=len(verdict.blocking_findings),
        severity_counts=sev_counts,
        category_counts={k: v for k, v in cat_counts.items() if v > 0},
        scanner_counts=scanner_counts,
        gate_passed=verdict.passed,
        gate_pass_rate_pct=gate_pass_rate,
        gate_coverage_pct=coverage_pct,
        expected_scanners=expected,
        executed_scanners=executed_list,
        sbom_present=sbom_ok,
        sbom_components_count=sbom_count,
        outdated_dependencies_count=len(outdated_deps),
        outdated_dependencies=outdated_deps,
        trend=trend_points,
        scanner_coverage=scanner_cov_items,
    )


def build_security_nexdash_dataset(metrics: SecurityPostureMetrics) -> dict[str, Any]:
    """Build semantic cube, query plan, KPIs, and rule-compliant security charts for NexDash."""
    cube = NexDashCubeSpec(
        name="security_posture",
        table="fact_security_findings",
        description="Metricas dos scanners de seguranca (SAST, SCA, secrets, containers, SBOM) e release gate.",
        dimensions=[
            NexDashDimensionSpec(name="project", type="string", description="Projeto analisado"),
            NexDashDimensionSpec(name="period", type="string", description="Periodo ou semana do scan"),
            NexDashDimensionSpec(name="severity", type="string", description="Severidade da vulnerabilidade"),
            NexDashDimensionSpec(name="scanner", type="string", description="Scanner de seguranca"),
            NexDashDimensionSpec(name="category", type="string", description="Categoria (sast, sca, secret, etc.)"),
        ],
        metrics=[
            NexDashMetricSpec(name="findings_count", aggregation="sum", column="findings_count"),
            NexDashMetricSpec(name="blocking_findings", aggregation="sum", column="blocking_findings"),
            NexDashMetricSpec(name="gate_coverage_pct", aggregation="avg", column="gate_coverage_pct"),
            NexDashMetricSpec(name="outdated_dependencies", aggregation="count", column="package_name"),
        ],
        allowed_filters=["project", "period", "severity", "scanner", "category"],
    )

    plan = NexDashQueryPlan(
        cube="security_posture",
        metrics=["findings_count", "blocking_findings", "gate_coverage_pct"],
        dimensions=["severity", "scanner", "period"],
        filters=[
            NexDashPlanFilter(field="project", operator="eq", value=metrics.project),
        ],
        limit=100,
    )

    crit_high = metrics.severity_counts.get("critical", 0) + metrics.severity_counts.get("high", 0)
    trend_delta = ""
    if len(metrics.trend) >= 2:
        first_tot = metrics.trend[0].total_active
        last_tot = metrics.trend[-1].total_active
        if first_tot > 0:
            pct = round(((last_tot - first_tot) / first_tot) * 100.0)
            sign = "+" if pct > 0 else ""
            trend_delta = f"{sign}{pct}%"

    kpis = [
        NexDashComputedKPI(
            id="critical_and_high",
            label="Vulnerabilidades Criticas e Altas",
            value=crit_high,
            formatted_value=str(crit_high),
            unit="findings",
            delta=f"{metrics.total_findings} ativas no total",
            comparison_label="meta: 0 criticas/altas",
            status="good" if crit_high == 0 else "critical",
        ),
        NexDashComputedKPI(
            id="release_gate_status",
            label="Status do Release Gate",
            value="APROVADO" if metrics.gate_passed else "BLOQUEADO",
            formatted_value="APROVADO" if metrics.gate_passed else "BLOQUEADO",
            delta=f"{metrics.gate_pass_rate_pct:.0f}% de aprovacao",
            comparison_label=f"politica {metrics.policy_name}",
            status="good" if metrics.gate_passed else "critical",
        ),
        NexDashComputedKPI(
            id="gate_coverage",
            label="Cobertura do Gate",
            value=metrics.gate_coverage_pct,
            formatted_value=f"{metrics.gate_coverage_pct:.0f}%",
            unit="%",
            delta=f"{len(metrics.executed_scanners)}/{len(metrics.expected_scanners)} scanners",
            comparison_label="SBOM incluso" if metrics.sbom_present else "sem SBOM",
            status="good" if metrics.gate_coverage_pct >= 85.0 else "warning",
        ),
        NexDashComputedKPI(
            id="outdated_dependencies",
            label="Dependencias com Atualizacao Recomendada",
            value=metrics.outdated_dependencies_count,
            formatted_value=str(metrics.outdated_dependencies_count),
            unit="pacotes",
            delta=f"{metrics.sbom_components_count} componentes no SBOM",
            comparison_label="via OSV / pip-audit",
            status="good" if metrics.outdated_dependencies_count == 0 else "warning",
        ),
    ]

    sev_order = ["critical", "high", "medium", "low", "info"]
    sev_labels = [s for s in sev_order if s in metrics.severity_counts]
    sev_values = [float(metrics.severity_counts[s]) for s in sev_labels]
    highest_nonzero_sev = next((s for s in sev_labels if metrics.severity_counts[s] > 0), "critical")

    sorted_scanners = sorted(metrics.scanner_coverage, key=lambda s: (-s.findings_count, s.scanner))
    top_scanner = sorted_scanners[0].scanner if sorted_scanners else None

    latest_period = metrics.trend[-1].period if metrics.trend else metrics.period

    charts = [
        NexDashComputedChart(
            id="vulnerabilities_by_severity",
            type="bar",
            title=(
                "Zero vulnerabilidades criticas ou altas ativas no ultimo scan"
                if crit_high == 0
                else f"{crit_high} vulnerabilidades criticas/altas exigem correcao antes do release"
            ),
            subtitle=f"Vulnerabilidades ativas por severidade, {metrics.period} (ocorrencias)",
            question="Qual a distribuicao das vulnerabilidades ativas por severidade?",
            x="Severidade",
            y="Vulnerabilidades ativas",
            unit="findings",
            labels=sev_labels,
            values=sev_values,
            highlight_label=highest_nonzero_sev,
            annotation=f"{metrics.suppressed_findings} ocorrencias suprimidas com justificativa auditada.",
            alt_text=(
                "Vulnerabilidades ativas por severidade: "
                + ", ".join(f"{s} ({metrics.severity_counts[s]})" for s in sev_labels)
            ),
        ),
        NexDashComputedChart(
            id="security_trend",
            type="line",
            title=(
                f"Vulnerabilidades ativas cairam {trend_delta} ao longo dos ciclos"
                if trend_delta.startswith("-")
                else f"Tendencia de vulnerabilidades ativas ({metrics.total_findings} no ultimo scan)"
            ),
            subtitle="Total de vulnerabilidades ativas por semana de scan (ocorrencias)",
            question="Como evoluiu o volume de vulnerabilidades ao longo do tempo?",
            x="Periodo",
            y="Vulnerabilidades ativas",
            unit="findings",
            labels=[t.period for t in metrics.trend],
            values=[float(t.total_active) for t in metrics.trend],
            highlight_label=latest_period,
            annotation="Gate de release exige zero vulnerabilidades criticas e altas.",
            alt_text=(
                "Tendencia de vulnerabilidades por periodo: "
                + ", ".join(f"{t.period} ({t.total_active})" for t in metrics.trend)
            ),
        ),
        NexDashComputedChart(
            id="findings_by_scanner",
            type="bar",
            title=(
                f"Cobertura do gate em {metrics.gate_coverage_pct:.0f}% "
                f"({len(metrics.executed_scanners)} scanners ativos)"
            ),
            subtitle="Ocorrencias ativas detectadas por scanner de seguranca (ocorrencias)",
            question="Quais scanners encontraram mais problemas no projeto?",
            x="Scanner",
            y="Ocorrencias ativas",
            unit="findings",
            labels=[s.scanner for s in sorted_scanners],
            values=[float(s.findings_count) for s in sorted_scanners],
            highlight_label=top_scanner,
            annotation=(
                f"Scanners executados: {', '.join(metrics.executed_scanners)}."
                if metrics.executed_scanners
                else "Nenhum scanner executado."
            ),
            alt_text=(
                "Ocorrencias por scanner: "
                + ", ".join(f"{s.scanner} ({s.findings_count})" for s in sorted_scanners)
            ),
        ),
    ]

    rows = [t.model_dump() for t in metrics.trend]
    gate_label = "APROVADO" if metrics.gate_passed else "BLOQUEADO"

    return {
        "title": (
            f"Postura de Seguranca ({metrics.project}): Gate {gate_label} "
            f"com {metrics.gate_coverage_pct:.0f}% de cobertura"
        ),
        "subtitle": f"Periodo {metrics.period} | Politica: {metrics.policy_name}",
        "cube": cube.model_dump(),
        "plan": plan.model_dump(),
        "kpis": [k.model_dump() for k in kpis],
        "charts": [c.model_dump() for c in charts],
        "rows": rows,
        "source_summary": (
            "Scanners nexcoder-security (semgrep, bandit, gitleaks, osv, pip-audit, trivy, syft) -> nexdash"
        ),
    }


def generate_security_dashboard(
    *,
    project: str = "nexcoder-platform",
    period: str = "2026-Q4",
    scan_result: ScanResult | None = None,
    history: list[tuple[str, ScanResult, GateVerdict]] | None = None,
    policy: GatePolicy | None = None,
    nexdash_client: NexDashClient | None = None,
    transport: TransportKind = "offline",
    nexdash_url: str = "http://127.0.0.1:8080",
    api_token: str | None = None,
) -> tuple[SecurityPostureMetrics, NexDashDashboardBundle]:
    """Compute security posture metrics from scanner results and build a NexDash dashboard."""
    active_policy = policy or GatePolicy(require_sbom=True)
    if history is None and scan_result is None:
        active_history = build_synthetic_security_scans(project=project, policy=active_policy)
        active_scan = active_history[-1][1]
    elif history is not None and scan_result is None:
        active_history = history
        active_scan = active_history[-1][1]
    else:
        assert scan_result is not None
        active_scan = scan_result
        active_history = history

    metrics = compute_security_metrics(
        active_scan,
        history=active_history,
        policy=active_policy,
        project=project,
        period=period,
    )
    dataset = build_security_nexdash_dataset(metrics)

    client = nexdash_client or NexDashClient(
        transport=transport,
        base_url=nexdash_url,
        api_token=api_token,
    )
    parameters = {
        "project": project,
        "period": period,
        "policy": active_policy.name,
    }
    bundle = client.generate_dashboard(
        model_id="security_posture",
        parameters=parameters,
        dataset=dataset,
    )
    return metrics, bundle
