# nexcoder-iac

Infrastructure as Code (IaC) generation, reference architecture catalog, user credential isolation, preview planning, and control plane audit for `nexcoder`.

---

## Capabilities

1. **High-Level to Multi-Target IaC Generation**:
   Transform plain descriptions (e.g., *"Python web app with PostgreSQL and Nginx"*) into production-grade infrastructure code.
   - **Local Target**: Docker Compose (`docker-compose.yml`, multi-service networking, volumes, AI serving integration).
   - **Single VM Target**: Ansible playbooks and inventories (`playbook.yml`, `inventory.ini`, UFW firewall, Docker systemd service).
   - **Cloud Targets**: Modular Terraform and OpenTofu configurations for **AWS**, **GCP**, **Azure**, **DigitalOcean**, and **Hetzner Cloud**.

2. **Reference Architecture Catalog**:
   - `simple_app`: Single server / container web app (FastAPI, Flask, Node, Go).
   - `app_database`: Web app + managed or containerized relational database (PostgreSQL, MySQL).
   - `queue_worker`: Web app + Redis broker + background worker + database.
   - `microservices`: API Gateway (Nginx) + Auth service + Core business service + PostgreSQL + Redis.
   - `ai_serving`: Web API + local or cloud AI inference server (vLLM or Ollama via `nexcoder-serving`) + vector-ready database.
   - Sizing tiers: `starter`, `standard`, and `production`.

3. **Strict User Credential Isolation**:
   - Never embeds secrets in code, `.tf` files, or playbooks.
   - All credentials read from standard environment variables (`AWS_ACCESS_KEY_ID`, `DO_TOKEN`, `HCLOUD_TOKEN`, etc.) or user `.env` files.
   - Generates `.env.example` templates with neutral dummy placeholders.
   - Built-in automated secret scanning blocks generation if credentials or private keys are accidentally present.

4. **Plan, Preview & Human Confirmation Gates**:
   - Generates deterministic plan previews detailing resource additions, modifications, and estimated monthly costs before execution.
   - `apply()` and `destroy()` actions require explicit confirmation (`confirm=True`) or validated approval tokens from the control plane.
   - Hermetic dry-run and offline simulation modes for zero-cloud testing.

5. **Control Plane Audit & Observability Integration**:
   - Reuses `nexcoder-control` tamper-evident append-only audit log (`AppendOnlyAuditLog`) to cryptographically record generation, planning, and apply events.
   - Reuses `nexcoder-agents` for agentic pipeline blocks with human-in-the-loop governance gates.
   - Reuses `nexcoder-serving` for AI inference deployment profiles.

---

## Installation

Install in editable mode:

```bash
pip install -e packages/iac
```

---

## Python Usage

### 1. Generate IaC from Natural Language

```python
from nexcoder_iac import IaCEngine, IaCTarget

engine = IaCEngine()

# Generate Terraform for AWS from a high-level description
artifacts = engine.generate(
    spec="Quero subir uma aplicacao FastAPI com Postgres e Nginx na AWS",
    target=IaCTarget.AWS,
)

for file in artifacts.files:
    print(f"File: {file.filename}")
```

### 2. Preview Plan and Apply with Confirmation Gate

```python
# Preview plan before applying
preview = engine.plan(artifacts, dry_run=True)
print(preview.execution_summary)

# Apply changes (requires explicit confirmation)
result = engine.apply(preview, confirm=True, dry_run=True)
print(f"Status: {result.status}")
```

### 3. Use Reference Architecture Catalog

```python
from nexcoder_iac import ArchitectureCatalog, ArchitectureTier, IaCTarget

# Retrieve microservices specification for Hetzner Cloud
spec = ArchitectureCatalog.get(
    "microservices",
    target=IaCTarget.HETZNER,
    tier=ArchitectureTier.PRODUCTION,
)
```

---

## CLI Usage

```bash
# List available reference architectures
nexcoder-iac catalog list

# Generate Docker Compose for local development
nexcoder-iac generate --desc "Python app with Redis and Postgres" --target local_compose --out-dir ./local-infra

# Generate Terraform for AWS
nexcoder-iac generate --desc "FastAPI with Postgres on AWS" --target aws --out-dir ./aws-infra

# Estimate monthly infrastructure cost
nexcoder-iac estimate --arch app_database --target digitalocean --tier standard
```
