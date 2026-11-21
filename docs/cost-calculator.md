# Product Cost Calculator: Build, Publish, Maintain, License, and Brand

The `nexcoder-planning` product cost calculator estimates the complete financial lifecycle of a software product or system: how much it costs to build (development), how much it costs to publish (domain, deployment setup, initial trademark and SSL), and how much it costs to sustain year over year and month over month (cloud infrastructure, managed database, backups, observability, e-mail, and IP renewal).

---

## Key Features

1. **Deterministic and Verifiable Pricing**: All prices are loaded from an editable YAML catalog (`pricing_catalog.yaml`), never hardcoded or guessed. Every line item references an official, public source (e.g., INPI Brazil, Registro.br, AWS Pricing Calculator, Hetzner Cloud, Google Cloud, DigitalOcean).
2. **Three-Scenario Modeling**: Generates three comprehensive projections for every estimate:
   - **Basic (MVP)**: Lean starter infrastructure, free observability tiers, focused feature scope.
   - **Medium (Recommended)**: Balanced standard infrastructure, automated offsite backups, commercial e-mail, standard APM, and official trademark registration.
   - **High (Enterprise)**: High-availability multi-AZ / redundant infrastructure, professional APM and WAF protection, redundant backups, and full legal IP advisory.
3. **Delivery Execution Modes**:
   - `human_team`: Based on squad sizing, hourly rates, and sprint hour allocations.
   - `ai_only`: Full autonomous agentic generation with human security oversight and token metering.
   - `hybrid`: Combined human architectural governance and AI agent execution.
4. **Control Plane Integration**: Connects with `nexcoder-control` metering (`CostTracker`) to inject actual runtime token consumption and dollar spend into development budgets.
5. **Infrastructure as Code (#95) Reuse**: Directly maps compute, database, and networking costs against `nexcoder-iac` targets (`local_compose`, `vm`, `hetzner`, `digitalocean`, `aws`, `gcp`) and tiers (`starter`, `standard`, `production`).
6. **Multi-Currency Governance**: Native support for `BRL` and `USD` with configurable exchange rates.
7. **Client Commercial Proposals**: Synthesizes client-facing executive markdown proposals with disbursement schedules and full price transparency for commercial and lead generation workflows.

---

## Input Specifications

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_name` | `str` | Required | Name of the project or product to evaluate. |
| `complexity` | `str` | `medium` | Scope complexity: `low`, `medium`, `high`, `enterprise`. |
| `feature_count` | `int` | `10` | Estimated number of functional features. |
| `estimated_screens` | `int` | `5` | Estimated frontend views or mobile screens. |
| `estimated_endpoints` | `int` | `12` | Estimated API endpoints or data integrations. |
| `mode` | `str` | `hybrid` | Delivery mode: `human_team`, `hybrid`, `ai_only`. |
| `infra_target` | `str` | `hetzner` | Infrastructure target: `hetzner`, `aws`, `digitalocean`, `gcp`, `vm`, `local_compose`. |
| `infra_tier` | `str` | `standard` | Sizing tier: `starter`, `standard`, `production`. |
| `domain_tld` | `str` | `com_br` | Domain TLD: `com_br`, `com`, `io`, `ai`. |
| `trademark_jurisdiction` | `str` | `inpi_br` | Trademark jurisdiction: `inpi_br`, `uspto_us`, `none`. |
| `currency` | `str` | `BRL` | Valuation currency: `BRL` or `USD`. |
| `exchange_rate` | `float` | `5.50` | USD to BRL exchange rate. |
| `include_proposal` | `bool` | `False` | Generate formatted commercial proposal markdown. |

---

## Output Breakdown Structure

For every scenario (`basic`, `medium`, `high`), the calculator produces:

1. **Development Cost**:
   - Engineering hours x weighted blended role rates (Senior, Mid, QA, DevOps, Lead Architect), or
   - Agent execution tokens x model pricing catalog + human security/audit oversight.
2. **Publication / Setup Cost**:
   - Initial domain registration.
   - Initial DevOps pipeline and server setup.
   - SSL/TLS provisioning.
   - Initial trademark application fees (official filing + advisory).
   - Initial software/plugin commercial license acquisition.
3. **Monthly Recurring Cost**:
   - Compute hosting (VM / container / serverless).
   - Database (containerized vs managed service).
   - Networking (egress bandwidth, load balancers, reverse proxy).
   - Corporate e-mail.
   - CDN, DNS, and WAF protection.
   - Offsite backups and object storage.
   - APM, logging, and AI token observability.
   - Monthly commercial SaaS licenses.
4. **Annual Recurring Cost**:
   - Consolidated 12-month recurring operating baseline.
   - Annual domain renewal fees.
   - Annual trademark amortized maintenance provision.
   - Annual software licenses.
5. **License and Brand Totals**:
   - Initial IP investment (trademark filing + initial domain + software setup).
   - Recurring annual IP investment (domain renewal + trademark decennial amortization).
6. **Consolidated Totals**:
   - **Year One Total**: Development + Publication + Annual Recurring + Contingency Buffer.
   - **Subsequent Years Total**: Annual Recurring.

---

## Python Usage Example

```python
from nexcoder_planning.cost import (
    CostScope,
    Currency,
    DevelopmentMode,
    InfrastructureTarget,
    InfrastructureTier,
    LicenseBrandSpec,
    ProductCostCalculator,
    ProductCostInput,
    ProviderSpec,
    ScopeComplexity,
    TeamSpec,
)

# 1. Define product scope and requirements
scope = CostScope(
    project_name="Portal Financeiro B2B",
    complexity=ScopeComplexity.MEDIUM,
    feature_count=12,
    estimated_screens=6,
    estimated_endpoints=18,
)

# 2. Configure providers and infrastructure
cost_input = ProductCostInput(
    scope=scope,
    mode=DevelopmentMode.HYBRID,
    team=TeamSpec(roles={"senior": 1, "mid": 1, "qa_engineer": 1}),
    providers=ProviderSpec(
        hosting_target=InfrastructureTarget.HETZNER,
        hosting_tier=InfrastructureTier.STANDARD,
        domain_tld="com_br",
        email_provider="google_workspace",
        cdn_security="cloudflare_free",
        monitoring="standard_cloud",
    ),
    license_brand=LicenseBrandSpec(
        trademark_jurisdiction="inpi_br",
        include_legal_assistance=True,
    ),
    currency=Currency.BRL,
    exchange_rate_usd_to_brl=5.50,
)

# 3. Calculate financial report across basic, medium, and high scenarios
calculator = ProductCostCalculator()
report = calculator.calculate(cost_input)

# 4. Print comparison table
print(report.summary_table())
```

---

## Control Plane Integration (Real AI Token Metering)

When running inside agentic pipelines, the calculator extracts real token consumption from `nexcoder-control`:

```python
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_planning.cost import extract_ai_spec_from_tracker, ProductCostCalculator, ProductCostInput, CostScope

tracker = CostTracker()
# ... agents execute and record token usage ...

ai_spec = extract_ai_spec_from_tracker(tracker, app_id="my_product")

cost_input = ProductCostInput(
    scope=CostScope(project_name="Agent-Built App"),
    ai=ai_spec,
)
report = ProductCostCalculator().calculate(cost_input)
```

---

## CLI Usage

The calculator is accessible through the unified `nexcoder` CLI:

```bash
# Calculate costs with formatted comparison table
nexcoder cost --project "E-Commerce API" --complexity medium --features 10 --currency BRL

# Generate a client commercial proposal
nexcoder cost --project "E-Commerce API" --proposal --client "Acme Corp"

# Output structured JSON
nexcoder cost --project "E-Commerce API" --json --out estimate.json
```
