"""Shared NexDash reporting protocol, MCP/REST client, and offline dashboard engine.

Connects nexcoder packages (planning and security) to nexdash for building
developer productivity and security posture dashboards. Supports three
transports:
- ``rest``: HTTP calls to nexdash REST endpoints (``/v1/models``, ``/v1/reports/generate``,
  ``/v1/dashboards/publish``) with Bearer or X-API-Key authentication.
- ``mcp``: JSON-RPC 2.0 calls to nexdash MCP tools (``nexdash_list_models``,
  ``nexdash_generate_report``, ``nexdash_publish_dashboard``).
- ``offline``: Deterministic local execution that validates parameters against
  semantic cube schemas and renders CSP-hardened HTML dashboards with
  ``window.NEXDASH_DATA`` injected in ``<head>``.
"""

from __future__ import annotations

import datetime as dt
import hmac
import html as html_lib
import json
import re
import uuid
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

NEXDASH_CSP = (
    "default-src 'self'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
QUALIFIED_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")
SQL_INJECTION_RE = re.compile(
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|ATTACH|PRAGMA)\b|--|/\*|\*/|;)",
    re.IGNORECASE,
)

ChartKind = Literal["bar", "line", "kpi", "table", "area"]
TransportKind = Literal["offline", "rest", "mcp"]
KPIStatus = Literal["neutral", "good", "warning", "critical"]


class NexDashError(Exception):
    """Base error for NexDash client and reporting operations."""


class NexDashValidationError(NexDashError, ValueError):
    """Raised when report parameters, identifiers, or cube plans are invalid."""


class NexDashAuthError(NexDashError, PermissionError):
    """Raised when authentication with NexDash fails."""


class NexDashTransportError(NexDashError, RuntimeError):
    """Raised when MCP or REST communication with NexDash fails."""


def validate_safe_identifier(value: str, label: str = "identifier") -> str:
    """Validate that a string is a safe SQL/cube identifier."""
    if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
        raise NexDashValidationError(f"Invalid {label} '{value}': must match ^[a-zA-Z_][a-zA-Z0-9_]*$")
    return value


def validate_qualified_identifier(value: str, label: str = "identifier") -> str:
    """Validate that a string is a safe qualified identifier (e.g. cube.field)."""
    if not isinstance(value, str) or not QUALIFIED_IDENTIFIER_RE.match(value):
        raise NexDashValidationError(f"Invalid {label} '{value}': must match qualified identifier pattern")
    return value


def validate_parameter_value(name: str, value: Any) -> Any:
    """Validate runtime parameter values to reject free SQL and malformed inputs."""
    validate_safe_identifier(name, "parameter name")
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise NexDashValidationError(f"Parameter '{name}' must not be an empty string.")
        if len(cleaned) > 256:
            raise NexDashValidationError(f"Parameter '{name}' exceeds maximum length of 256 characters.")
        if SQL_INJECTION_RE.search(cleaned):
            raise NexDashValidationError(
                f"Parameter '{name}' contains forbidden SQL keywords or characters: '{cleaned}'"
            )
        return cleaned
    if isinstance(value, list | tuple):
        if len(value) == 0:
            raise NexDashValidationError(f"Parameter '{name}' list must not be empty.")
        return [validate_parameter_value(name, item) for item in value]
    raise NexDashValidationError(f"Unsupported type for parameter '{name}': {type(value).__name__}")


def safe_json_for_script(value: Any) -> str:
    """Serialize value to JSON safe for embedding inside an HTML <script> block.

    Escapes '<', '>', '&', U+2028, and U+2029 so strings like '</script>' or '<!--'
    cannot break out of the script element.
    """
    raw = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


class NexDashDimensionSpec(BaseModel):
    """Dimension definition in a semantic cube."""

    name: str
    column: str | None = None
    type: str = "string"
    description: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_safe_identifier(v, "dimension name")


class NexDashMetricSpec(BaseModel):
    """Metric definition in a semantic cube."""

    name: str
    aggregation: Literal["count", "count_distinct", "sum", "avg", "min", "max"] = "sum"
    column: str = "*"
    description: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_safe_identifier(v, "metric name")


class NexDashCubeSpec(BaseModel):
    """Declarative semantic cube compatible with nexdash.Cube."""

    name: str
    table: str
    description: str = ""
    dimensions: list[NexDashDimensionSpec] = Field(default_factory=list)
    metrics: list[NexDashMetricSpec] = Field(default_factory=list)
    allowed_filters: list[str] = Field(default_factory=list)

    @field_validator("name", "table")
    @classmethod
    def _check_id(cls, v: str) -> str:
        return validate_safe_identifier(v, "cube identifier")


class NexDashPlanFilter(BaseModel):
    """Parameterized filter on a cube dimension."""

    field: str
    operator: str = "eq"
    value: Any = None

    @field_validator("field")
    @classmethod
    def _check_field(cls, v: str) -> str:
        return validate_qualified_identifier(v, "filter field")


class NexDashQueryPlan(BaseModel):
    """Validated query plan targeting a semantic cube (never raw SQL)."""

    cube: str
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[NexDashPlanFilter] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=10000)

    @field_validator("cube")
    @classmethod
    def _check_cube(cls, v: str) -> str:
        return validate_safe_identifier(v, "query plan cube")

    @field_validator("metrics", "dimensions")
    @classmethod
    def _check_fields(cls, items: list[str]) -> list[str]:
        return [validate_qualified_identifier(item, "plan field") for item in items]


class NexDashComputedKPI(BaseModel):
    """Top-level KPI card with comparison context."""

    id: str
    label: str
    value: float | int | str
    formatted_value: str
    unit: str = ""
    delta: str = ""
    comparison_label: str = ""
    status: KPIStatus = "neutral"

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        return validate_safe_identifier(v, "kpi id")


class NexDashComputedChart(BaseModel):
    """Computed chart series following visualization best practices."""

    id: str
    type: ChartKind = "bar"
    title: str
    subtitle: str = ""
    question: str = ""
    x: str
    y: str
    unit: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    highlight_label: str | None = None
    annotation: str = ""
    alt_text: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        return validate_safe_identifier(v, "chart id")


class NexDashModelDescriptor(BaseModel):
    """Metadata describing a ready-made report model in NexDash."""

    model_id: str
    title: str
    description: str
    cube_name: str
    allowed_parameters: list[str] = Field(default_factory=list)
    required_parameters: list[str] = Field(default_factory=list)


class NexDashDashboardBundle(BaseModel):
    """Complete report and renderable HTML dashboard returned by NexDash."""

    status: str = "success"
    dashboard_id: str = Field(default_factory=lambda: f"dash_{uuid.uuid4().hex[:12]}")
    model_id: str
    title: str
    subtitle: str
    transport: TransportKind = "offline"
    parameters: dict[str, Any] = Field(default_factory=dict)
    cube: NexDashCubeSpec
    plan: NexDashQueryPlan
    kpis: list[NexDashComputedKPI] = Field(default_factory=list)
    charts: list[NexDashComputedChart] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    html: str = ""
    csp_header: str = NEXDASH_CSP
    generated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    source_summary: str = ""


def _format_number_pt_br(val: float | int, unit: str = "") -> str:
    """Format numbers cleanly without useless decimals."""
    if isinstance(val, int) or (isinstance(val, float) and val.is_integer()):
        formatted = f"{int(val):,}".replace(",", ".")
    else:
        formatted = f"{val:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if not unit:
        return formatted
    if unit == "%":
        return f"{formatted}%"
    return f"{formatted} {unit}"


def render_nexdash_html(
    *,
    title: str,
    subtitle: str,
    parameters: dict[str, Any],
    kpis: list[NexDashComputedKPI],
    charts: list[NexDashComputedChart],
    rows: list[dict[str, Any]],
    source_summary: str,
    generated_at: str,
    model_id: str,
) -> str:
    """Render a CSP-compliant HTML dashboard with server-injected NEXDASH_DATA.

    Follows graficos-com-regras:
    - 3 to 5 KPIs at the top with comparison context (Z-pattern reading).
    - Visible filter state bar.
    - Horizontal bar charts starting at zero and ordered by value, or line charts for trends.
    - Direct value labels with units; one highlighted item in Okabe-Ito blue (#0072B2) or
      vermilion (#D55E00), remaining items in neutral slate (#64748B).
    - Accessible data table and aria-label alt text for every chart.
    - Strict Content-Security-Policy with connect-src 'none'.
    """
    dataset_payload = {
        "model_id": model_id,
        "title": title,
        "subtitle": subtitle,
        "parameters": parameters,
        "kpis": [k.model_dump() for k in kpis],
        "charts": [c.model_dump() for c in charts],
        "rows": rows,
    }
    meta_payload = {
        "updated_at": generated_at,
        "source_summary": source_summary,
        "refreshable": False,
        "csp": "connect-src 'none'",
    }

    safe_data_json = safe_json_for_script(dataset_payload)
    safe_meta_json = safe_json_for_script(meta_payload)

    filter_pills: list[str] = []
    for k, v in parameters.items():
        val_str = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        filter_pills.append(
            f'<span class="filter-pill"><strong>{html_lib.escape(k)}:</strong> {html_lib.escape(val_str)}</span>'
        )
    filters_html = "\n          ".join(filter_pills) if filter_pills else '<span class="filter-pill">All data</span>'

    kpi_cards: list[str] = []
    status_colors = {
        "good": "#0072B2",
        "warning": "#E69F00",
        "critical": "#D55E00",
        "neutral": "#334155",
    }
    for kpi in kpis[:5]:
        border_color = status_colors.get(kpi.status, "#334155")
        delta_html = ""
        if kpi.delta or kpi.comparison_label:
            delta_text = f"{kpi.delta} {kpi.comparison_label}".strip()
            delta_html = f'<div class="kpi-delta">{html_lib.escape(delta_text)}</div>'
        kpi_cards.append(
            f"""        <article class="kpi-card" style="border-top: 3px solid {border_color};">
          <div class="kpi-label">{html_lib.escape(kpi.label)}</div>
          <div class="kpi-value">{html_lib.escape(kpi.formatted_value)}</div>
          {delta_html}
        </article>"""
        )
    kpis_html = "\n".join(kpi_cards)

    chart_sections: list[str] = []
    for chart in charts:
        max_val = max([abs(v) for v in chart.values], default=1.0) or 1.0
        bars_html_list: list[str] = []
        table_rows_list: list[str] = []

        for label, val in zip(chart.labels, chart.values, strict=False):
            pct = max(2.0, min(100.0, (max(0.0, val) / max_val) * 100.0)) if max_val > 0 else 0.0
            is_highlight = chart.highlight_label is not None and label == chart.highlight_label
            fill_color = "#0072B2" if is_highlight else "#64748B"
            if chart.id == "vulnerabilities_by_severity" and is_highlight:
                fill_color = "#D55E00"
            weight = "600" if is_highlight else "400"
            formatted_val = _format_number_pt_br(val, chart.unit)
            marker = " (destaque)" if is_highlight else ""

            bars_html_list.append(
                f"""            <div class="bar-row" style="font-weight: {weight};">
              <div class="bar-label">{html_lib.escape(str(label))}</div>
              <div class="bar-track" aria-hidden="true">
                <div class="bar-fill" style="width: {pct:.1f}%; background: {fill_color};"></div>
              </div>
              <div class="bar-value">{html_lib.escape(formatted_val)}</div>
            </div>"""
            )
            table_rows_list.append(
                f"              <tr><td>{html_lib.escape(str(label))}{html_lib.escape(marker)}</td>"
                f"<td>{html_lib.escape(formatted_val)}</td></tr>"
            )

        annotation_html = (
            f'<p class="chart-annotation">{html_lib.escape(chart.annotation)}</p>' if chart.annotation else ""
        )
        bars_block = "\n".join(bars_html_list)
        table_block = "\n".join(table_rows_list)
        alt_attr = html_lib.escape(chart.alt_text or chart.title)

        chart_sections.append(
            f"""        <section class="chart-card" role="figure" aria-label="{alt_attr}">
          <header class="chart-header">
            <h3>{html_lib.escape(chart.title)}</h3>
            <p class="chart-subtitle">{html_lib.escape(chart.subtitle)}</p>
          </header>
          <div class="chart-body" data-chart-type="{html_lib.escape(chart.type)}">
{bars_block}
          </div>
          {annotation_html}
          <details class="chart-data-table">
            <summary>Tabela de dados ({html_lib.escape(chart.x)} vs {html_lib.escape(chart.y)})</summary>
            <table role="table">
              <thead>
                <tr><th scope="col">{html_lib.escape(chart.x)}</th><th scope="col">{html_lib.escape(chart.y)}</th></tr>
              </thead>
              <tbody>
{table_block}
              </tbody>
            </table>
          </details>
        </section>"""
        )

    charts_html = "\n".join(chart_sections)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="{NEXDASH_CSP}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_lib.escape(title)}</title>
  <script id="nexdash-data">window.NEXDASH_DATA={safe_data_json};window.NEXDASH_META={safe_meta_json};</script>
  <style>
    :root {{
      --bg: #F8FAFC;
      --surface: #FFFFFF;
      --text: #0F172A;
      --muted: #475569;
      --border: #E2E8F0;
      --accent: #0072B2;
      --alert: #D55E00;
      --neutral: #64748B;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .container {{ max-width: 1160px; margin: 0 auto; }}
    .page-header {{ margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
    .page-header h1 {{ margin: 0 0 6px 0; font-size: 1.5rem; font-weight: 700; color: var(--text); }}
    .page-subtitle {{ margin: 0 0 12px 0; font-size: 0.95rem; color: var(--muted); }}
    .filters-bar {{ display: flex; flex-wrap: wrap; gap: 8px; font-size: 0.85rem; }}
    .filter-pill {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 4px 10px;
      color: var(--text);
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px;
    }}
    .kpi-label {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 6px; }}
    .kpi-value {{ font-size: 1.75rem; font-weight: 700; color: var(--text); }}
    .kpi-delta {{ font-size: 0.8rem; color: var(--muted); margin-top: 6px; }}
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }}
    .chart-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 20px;
    }}
    .chart-header h3 {{ margin: 0 0 4px 0; font-size: 1.05rem; color: var(--text); }}
    .chart-subtitle {{ margin: 0 0 16px 0; font-size: 0.85rem; color: var(--muted); }}
    .bar-row {{
      display: grid;
      grid-template-columns: 150px 1fr 90px;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
      font-size: 0.88rem;
    }}
    .bar-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }}
    .bar-track {{ background: #F1F5F9; height: 18px; border-radius: 3px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 3px; }}
    .bar-value {{ text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }}
    .chart-annotation {{
      margin: 12px 0 0 0;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .chart-data-table {{ margin-top: 12px; font-size: 0.82rem; color: var(--muted); }}
    .chart-data-table table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    .chart-data-table th, .chart-data-table td {{
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid var(--border);
      color: var(--text);
    }}
    .page-footer {{
      border-top: 1px solid var(--border);
      padding-top: 12px;
      font-size: 0.8rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
    }}
  </style>
</head>
<body>
  <main class="container">
    <header class="page-header">
      <h1>{html_lib.escape(title)}</h1>
      <p class="page-subtitle">{html_lib.escape(subtitle)}</p>
      <div class="filters-bar" aria-label="Filtros ativos">
        {filters_html}
      </div>
    </header>
    <section class="kpi-grid" aria-label="Indicadores principais">
{kpis_html}
    </section>
    <div class="charts-grid">
{charts_html}
    </div>
    <footer class="page-footer">
      <span>Fonte: {html_lib.escape(source_summary)}</span>
      <span>Atualizado em: {html_lib.escape(generated_at)}</span>
    </footer>
  </main>
</body>
</html>
"""


class LocalNexDashEngine:
    """Deterministic in-memory NexDash reporting engine with strict parameter validation.

    Used in offline mode and by the MCP/REST mock servers for reproducible tests.
    """

    def __init__(self) -> None:
        self._models: dict[str, NexDashModelDescriptor] = {
            "dev_productivity": NexDashModelDescriptor(
                model_id="dev_productivity",
                title="Produtividade de Engenharia de Software",
                description=(
                    "PRs abertos e mesclados, tempo de review, lead time, issues fechadas e throughput por pessoa/time."
                ),
                cube_name="dev_productivity",
                allowed_parameters=["project", "team", "period", "platforms"],
                required_parameters=["project", "period"],
            ),
            "security_posture": NexDashModelDescriptor(
                model_id="security_posture",
                title="Postura de Seguranca e Cobertura do Release Gate",
                description=(
                    "Vulnerabilidades por severidade, tendencia no tempo, cobertura dos scanners "
                    "no gate e dependencias desatualizadas."
                ),
                cube_name="security_posture",
                allowed_parameters=["project", "period", "policy", "severity_filter"],
                required_parameters=["project", "period"],
            ),
        }
        self._published: dict[str, dict[str, Any]] = {}

    def list_models(self) -> list[NexDashModelDescriptor]:
        """Return all registered report models."""
        return list(self._models.values())

    def validate_request(self, model_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Validate model_id and runtime parameters against the model allowlist."""
        validate_safe_identifier(model_id, "model_id")
        if model_id not in self._models:
            raise NexDashValidationError(
                f"Unknown report model '{model_id}'. Available models: {sorted(self._models.keys())}"
            )
        descriptor = self._models[model_id]
        if not isinstance(parameters, dict):
            raise NexDashValidationError("Report parameters must be a JSON object.")

        validated_params: dict[str, Any] = {}
        allowed = set(descriptor.allowed_parameters)
        for key, raw_val in parameters.items():
            validate_safe_identifier(key, "parameter name")
            if key not in allowed:
                raise NexDashValidationError(
                    f"Parameter '{key}' is not allowed for model '{model_id}'. Allowed: {sorted(allowed)}"
                )
            validated_params[key] = validate_parameter_value(key, raw_val)

        for req_key in descriptor.required_parameters:
            if req_key not in validated_params or validated_params[req_key] is None:
                raise NexDashValidationError(
                    f"Missing required parameter '{req_key}' for model '{model_id}'."
                )

        return validated_params

    def generate_report(
        self,
        model_id: str,
        parameters: dict[str, Any],
        dataset: dict[str, Any],
        transport: TransportKind = "offline",
    ) -> NexDashDashboardBundle:
        """Validate parameters and build a complete NexDashDashboardBundle."""
        validated_params = self.validate_request(model_id, parameters)
        if not isinstance(dataset, dict):
            raise NexDashValidationError("Dataset payload must be a dictionary.")

        cube_data = dataset.get("cube")
        plan_data = dataset.get("plan")
        kpis_data = dataset.get("kpis", [])
        charts_data = dataset.get("charts", [])
        rows_data = dataset.get("rows", [])
        title = str(dataset.get("title") or self._models[model_id].title)
        subtitle = str(dataset.get("subtitle") or self._models[model_id].description)
        source_summary = str(dataset.get("source_summary") or f"nexcoder -> nexdash ({model_id})")
        generated_at = str(dataset.get("generated_at") or dt.datetime.now(dt.UTC).isoformat())

        cube = (
            NexDashCubeSpec.model_validate(cube_data)
            if cube_data
            else NexDashCubeSpec(
                name=model_id,
                table=f"fact_{model_id}",
                description=self._models[model_id].description,
            )
        )
        plan = (
            NexDashQueryPlan.model_validate(plan_data)
            if plan_data
            else NexDashQueryPlan(
                cube=cube.name,
                metrics=[m.name for m in cube.metrics] or ["total_count"],
                dimensions=[d.name for d in cube.dimensions][:2],
                filters=[
                    NexDashPlanFilter(field=k, operator="eq", value=v)
                    for k, v in validated_params.items()
                    if isinstance(v, str | int | float)
                ],
            )
        )
        kpis = [NexDashComputedKPI.model_validate(k) for k in kpis_data]
        charts = [NexDashComputedChart.model_validate(c) for c in charts_data]

        rendered_html = render_nexdash_html(
            title=title,
            subtitle=subtitle,
            parameters=validated_params,
            kpis=kpis,
            charts=charts,
            rows=rows_data,
            source_summary=source_summary,
            generated_at=generated_at,
            model_id=model_id,
        )

        return NexDashDashboardBundle(
            status="success",
            model_id=model_id,
            title=title,
            subtitle=subtitle,
            transport=transport,
            parameters=validated_params,
            cube=cube,
            plan=plan,
            kpis=kpis,
            charts=charts,
            rows=rows_data,
            total_rows=len(rows_data),
            html=rendered_html,
            csp_header=NEXDASH_CSP,
            generated_at=generated_at,
            source_summary=source_summary,
        )

    def publish_dashboard(self, bundle: NexDashDashboardBundle, cadence: str = "daily") -> dict[str, Any]:
        """Register a rendered dashboard in the engine store and return access metadata."""
        if cadence not in ("never", "hourly", "daily", "weekly"):
            raise NexDashValidationError(f"Invalid dashboard refresh cadence '{cadence}'.")
        record = {
            "status": "published",
            "dashboard_id": bundle.dashboard_id,
            "model_id": bundle.model_id,
            "title": bundle.title,
            "cadence": cadence,
            "csp_header": bundle.csp_header,
            "url": f"http://127.0.0.1:8080/d/{bundle.dashboard_id}",
            "published_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        self._published[bundle.dashboard_id] = record
        return record


class NexDashMockMCPServer:
    """In-memory MCP JSON-RPC 2.0 server exposing NexDash shared report engine tools."""

    def __init__(self, engine: LocalNexDashEngine | None = None, api_token: str | None = None) -> None:
        self.engine = engine or LocalNexDashEngine()
        self._api_token = api_token

    def verify_token(self, provided_token: str | None) -> bool:
        """Verify token in constant time when authentication is configured."""
        if not self._api_token:
            return True
        if not provided_token:
            return False
        return hmac.compare_digest(provided_token.encode("utf-8"), self._api_token.encode("utf-8"))

    def handle_jsonrpc(self, request_payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """Handle a single JSON-RPC 2.0 request for NexDash MCP tools."""
        req_id = request_payload.get("id")
        method = request_payload.get("method", "")
        params = request_payload.get("params") or {}

        if not self.verify_token(token):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": "Unauthorized: invalid or missing NexDash API token."},
            }

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "nexdash-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "nexdash_list_models",
                            "description": "List available parameterized report models in NexDash.",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "nexdash_generate_report",
                            "description": "Generate a validated report and CSP-safe HTML dashboard from a model.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "model_id": {"type": "string"},
                                    "parameters": {"type": "object"},
                                    "dataset": {"type": "object"},
                                },
                                "required": ["model_id", "parameters", "dataset"],
                            },
                        },
                        {
                            "name": "nexdash_publish_dashboard",
                            "description": "Publish a generated dashboard with scheduled refresh cadence.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "bundle": {"type": "object"},
                                    "cadence": {"type": "string", "default": "daily"},
                                },
                                "required": ["bundle"],
                            },
                        },
                    ]
                },
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            try:
                if tool_name == "nexdash_list_models":
                    models = [m.model_dump() for m in self.engine.list_models()]
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps({"models": models})}],
                            "isError": False,
                        },
                    }
                if tool_name == "nexdash_generate_report":
                    bundle = self.engine.generate_report(
                        model_id=str(arguments.get("model_id", "")),
                        parameters=arguments.get("parameters") or {},
                        dataset=arguments.get("dataset") or {},
                        transport="mcp",
                    )
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": bundle.model_dump_json()}],
                            "isError": False,
                        },
                    }
                if tool_name == "nexdash_publish_dashboard":
                    bundle_obj = NexDashDashboardBundle.model_validate(arguments.get("bundle") or {})
                    pub = self.engine.publish_dashboard(
                        bundle=bundle_obj,
                        cadence=str(arguments.get("cadence", "daily")),
                    )
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(pub)}],
                            "isError": False,
                        },
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool '{tool_name}'"},
                }
            except NexDashValidationError as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"status": "validation_error", "detail": str(exc)}),
                            }
                        ],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method '{method}'"},
        }


def create_nexdash_mock_transport(
    engine: LocalNexDashEngine | None = None,
    api_token: str | None = None,
) -> httpx.MockTransport:
    """Create an httpx.MockTransport that serves NexDash REST and MCP endpoints offline."""
    active_engine = engine or LocalNexDashEngine()
    mcp_server = NexDashMockMCPServer(engine=active_engine, api_token=api_token)

    def _extract_token(request: httpx.Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return request.headers.get("X-API-Key")

    def _handler(request: httpx.Request) -> httpx.Response:
        token = _extract_token(request)
        if not mcp_server.verify_token(token):
            return httpx.Response(
                status_code=401,
                json={"detail": "Unauthorized: invalid or missing NexDash API token."},
            )

        path = request.url.path
        if request.method == "GET" and path == "/v1/models":
            models = [m.model_dump() for m in active_engine.list_models()]
            return httpx.Response(status_code=200, json={"models": models})

        if request.method == "POST" and path == "/v1/reports/generate":
            try:
                body = json.loads(request.content.decode("utf-8"))
                bundle = active_engine.generate_report(
                    model_id=str(body.get("model_id", "")),
                    parameters=body.get("parameters") or {},
                    dataset=body.get("dataset") or {},
                    transport="rest",
                )
                return httpx.Response(
                    status_code=200,
                    json=bundle.model_dump(),
                    headers={"Content-Security-Policy": NEXDASH_CSP},
                )
            except NexDashValidationError as exc:
                return httpx.Response(status_code=422, json={"detail": str(exc)})

        if request.method == "POST" and path == "/v1/dashboards/publish":
            try:
                body = json.loads(request.content.decode("utf-8"))
                bundle_obj = NexDashDashboardBundle.model_validate(body.get("bundle") or {})
                pub = active_engine.publish_dashboard(
                    bundle=bundle_obj,
                    cadence=str(body.get("cadence", "daily")),
                )
                return httpx.Response(status_code=200, json=pub)
            except NexDashValidationError as exc:
                return httpx.Response(status_code=422, json={"detail": str(exc)})

        if request.method == "POST" and path in ("/messages", "/mcp"):
            body = json.loads(request.content.decode("utf-8"))
            rpc_resp = mcp_server.handle_jsonrpc(body, token=token)
            return httpx.Response(status_code=200, json=rpc_resp)

        return httpx.Response(status_code=404, json={"detail": f"Endpoint {path} not found"})

    return httpx.MockTransport(_handler)


class NexDashClient:
    """Client for communicating with NexDash report engine via Offline, MCP, or REST."""

    def __init__(
        self,
        transport: TransportKind = "offline",
        base_url: str = "http://127.0.0.1:8080",
        api_token: str | None = None,
        http_client: httpx.Client | None = None,
        mcp_handler: Callable[[dict[str, Any], str | None], dict[str, Any]] | None = None,
        engine: LocalNexDashEngine | None = None,
    ) -> None:
        if transport not in ("offline", "rest", "mcp"):
            raise NexDashValidationError(f"Unsupported transport '{transport}'. Expected offline, rest, or mcp.")
        self.transport: TransportKind = transport
        self.base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._custom_http_client = http_client
        self._http_client: httpx.Client | None = None
        self.engine = engine or LocalNexDashEngine()
        self._mcp_server = NexDashMockMCPServer(engine=self.engine, api_token=None)
        self._mcp_handler = mcp_handler

    def __repr__(self) -> str:
        masked = "***" if self._api_token else "None"
        return f"NexDashClient(transport={self.transport!r}, base_url={self.base_url!r}, api_token={masked})"

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "nexcoder-nexdash-client"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
            headers["X-API-Key"] = self._api_token
        return headers

    def _get_http_client(self) -> httpx.Client:
        if self._custom_http_client is not None:
            return self._custom_http_client
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def close(self) -> None:
        """Close owned HTTP client."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def list_models(self) -> list[NexDashModelDescriptor]:
        """List available report models from NexDash."""
        if self.transport == "offline":
            return self.engine.list_models()

        if self.transport == "rest":
            client = self._get_http_client()
            resp = client.get(f"{self.base_url}/v1/models", headers=self._get_headers())
            if resp.status_code == 401:
                raise NexDashAuthError("NexDash REST authentication failed (401).")
            resp.raise_for_status()
            data = resp.json()
            return [NexDashModelDescriptor.model_validate(item) for item in data.get("models", [])]

        # MCP transport
        rpc_req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": "nexdash_list_models", "arguments": {}},
        }
        rpc_resp = self._call_mcp(rpc_req)
        content_text = self._extract_mcp_text(rpc_resp)
        parsed = json.loads(content_text)
        return [NexDashModelDescriptor.model_validate(item) for item in parsed.get("models", [])]

    def generate_dashboard(
        self,
        model_id: str,
        parameters: dict[str, Any],
        dataset: dict[str, Any],
    ) -> NexDashDashboardBundle:
        """Send normalized metrics and parameters to NexDash and receive a rendered dashboard bundle."""
        if self.transport == "offline":
            return self.engine.generate_report(
                model_id=model_id,
                parameters=parameters,
                dataset=dataset,
                transport="offline",
            )

        if self.transport == "rest":
            client = self._get_http_client()
            payload = {"model_id": model_id, "parameters": parameters, "dataset": dataset}
            resp = client.post(
                f"{self.base_url}/v1/reports/generate",
                json=payload,
                headers=self._get_headers(),
            )
            if resp.status_code == 401:
                raise NexDashAuthError("NexDash REST authentication failed (401).")
            if resp.status_code == 422:
                detail = resp.json().get("detail", "Invalid report parameters")
                raise NexDashValidationError(str(detail))
            resp.raise_for_status()
            return NexDashDashboardBundle.model_validate(resp.json())

        # MCP transport
        rpc_req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": "nexdash_generate_report",
                "arguments": {
                    "model_id": model_id,
                    "parameters": parameters,
                    "dataset": dataset,
                },
            },
        }
        rpc_resp = self._call_mcp(rpc_req)
        content_text = self._extract_mcp_text(rpc_resp)
        return NexDashDashboardBundle.model_validate_json(content_text)

    def publish_dashboard(self, bundle: NexDashDashboardBundle, cadence: str = "daily") -> dict[str, Any]:
        """Publish a generated dashboard in NexDash."""
        if self.transport == "offline":
            return self.engine.publish_dashboard(bundle=bundle, cadence=cadence)

        if self.transport == "rest":
            client = self._get_http_client()
            resp = client.post(
                f"{self.base_url}/v1/dashboards/publish",
                json={"bundle": bundle.model_dump(), "cadence": cadence},
                headers=self._get_headers(),
            )
            if resp.status_code == 401:
                raise NexDashAuthError("NexDash REST authentication failed (401).")
            if resp.status_code == 422:
                detail = resp.json().get("detail", "Invalid publish parameters")
                raise NexDashValidationError(str(detail))
            resp.raise_for_status()
            return resp.json()

        rpc_req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": "nexdash_publish_dashboard",
                "arguments": {"bundle": bundle.model_dump(), "cadence": cadence},
            },
        }
        rpc_resp = self._call_mcp(rpc_req)
        content_text = self._extract_mcp_text(rpc_resp)
        return json.loads(content_text)

    def _call_mcp(self, rpc_req: dict[str, Any]) -> dict[str, Any]:
        if self._mcp_handler is not None:
            return self._mcp_handler(rpc_req, self._api_token)
        if self._custom_http_client is not None:
            resp = self._custom_http_client.post(
                f"{self.base_url}/messages",
                json=rpc_req,
                headers=self._get_headers(),
            )
            if resp.status_code == 401:
                raise NexDashAuthError("NexDash MCP HTTP authentication failed (401).")
            resp.raise_for_status()
            return resp.json()
        return self._mcp_server.handle_jsonrpc(rpc_req, token=self._api_token)

    @staticmethod
    def _extract_mcp_text(rpc_resp: dict[str, Any]) -> str:
        if "error" in rpc_resp and rpc_resp["error"]:
            err = rpc_resp["error"]
            code = err.get("code")
            msg = err.get("message", "MCP error")
            if code == -32001:
                raise NexDashAuthError(msg)
            raise NexDashTransportError(f"MCP error ({code}): {msg}")

        result = rpc_resp.get("result") or {}
        content = result.get("content") or []
        text = content[0].get("text", "{}") if content else "{}"
        if result.get("isError"):
            try:
                err_data = json.loads(text)
                detail = err_data.get("detail") or text
            except Exception:
                detail = text
            raise NexDashValidationError(str(detail))
        return text
