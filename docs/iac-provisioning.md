# Infrastructure as Code: Provisioning Servers, VMs, and Architectures

This guide explains how `nexcoder-iac` enables provisioning infrastructure from natural language descriptions or structured specifications, from basic single-server deployments to advanced multi-service cloud topologies.

---

## Architectural Principles

1. **Multi-Target Portability**: Deploy the same logical architecture to local development (Docker Compose), a dedicated server or VPS (Ansible), or major cloud providers (AWS, GCP, Azure, DigitalOcean, Hetzner Cloud via Terraform/OpenTofu).
2. **User Credential Isolation**: NexCoder generates infrastructure code and runs plan previews, but **never supplies or stores cloud credentials**. Cloud infrastructure is provisioned strictly within the user's own cloud accounts using credentials loaded from local environment variables.
3. **Plan Before Apply**: Every infrastructure modification requires an upfront plan preview detailing additions, changes, and estimated monthly costs. Execution (`apply` or `destroy`) is strictly gated by explicit human confirmation or a control plane approval token.
4. **Control Plane Governance**: Every generation, plan, apply, and destroy action is cryptographically recorded in `nexcoder-control` append-only audit log with SHA-256 hash chaining.

---

## Reference Architecture Catalog

`nexcoder-iac` includes a reference architecture catalog covering five common topologies with three sizing tiers (`starter`, `standard`, `production`):

| Architecture ID | Description | Typical Components |
|---|---|---|
| `simple_app` | Basic single server or container | Python / Node / Go web service |
| `app_database` | Web app + relational database | Web service + PostgreSQL / MySQL + Reverse Proxy (Nginx) |
| `queue_worker` | Asynchronous task processing | Web API + Redis broker + Background worker + PostgreSQL |
| `microservices` | Distributed service platform | API Gateway + Auth service + Core service + Redis + PostgreSQL |
| `ai_serving` | LLM and RAG inference engine | Web API + vLLM or Ollama serving node + Knowledge Database |

### Sizing Tiers

- **`starter`**: Minimum resource footprint suitable for development and prototypes (e.g. 0.5 vCPU, 512MB RAM, single container/VM, non-HA database).
- **`standard`**: Balanced resource allocation for production workloads with moderate traffic (e.g. 1-2 vCPU, 2-4GB RAM, managed database, automatic restart).
- **`production`**: High-availability configuration with multi-instance replicas, managed database clusters, load balancing, and health checks.

---

## User Credentials and Security

Cloud providers require account credentials to provision infrastructure. NexCoder enforces strict security boundaries:

1. **No Embedded Secrets**: Generated `.tf`, `.yml`, and script files never contain hardcoded tokens, passwords, or private keys.
2. **Environment Variable Injection**: Credentials are read from standard environment variables:
   - **AWS**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
   - **GCP**: `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT_ID`, `GCP_REGION`
   - **Azure**: `ARM_SUBSCRIPTION_ID`, `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`
   - **DigitalOcean**: `DIGITALOCEAN_TOKEN`
   - **Hetzner Cloud**: `HCLOUD_TOKEN`
   - **Dedicated VM / Server**: `SERVER_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY_PATH`
3. **Automated Secret Scanning**: The generator automatically scans all output files with regex heuristics for AWS keys, private keys, and plain passwords before writing them to disk.
4. **Safe Templates**: A `.env.example` file is generated containing only safe placeholders (e.g. `your_aws_access_key_id_here`).

---

## Python API Usage

### 1. Generating IaC from Natural Language

```python
from nexcoder_iac import IaCEngine, IaCTarget

engine = IaCEngine()

# High-level prompt automatically parsed into an ArchitectureSpec
artifacts = engine.generate(
    spec="Quero subir uma aplicacao FastAPI com Postgres e nginx na AWS",
    target=IaCTarget.AWS,
)

print(f"Target: {artifacts.target.value}")
print(f"Tool:   {artifacts.tool.value}")
print(f"Estimated Monthly Cost: ${artifacts.estimated_monthly_cost_usd:.2f} USD")

for f in artifacts.files:
    print(f"  - {f.filename} ({f.file_type})")
```

### 2. Previewing Plan and Applying with Confirmation Gate

```python
# Generate deterministic preview of planned resources
preview = engine.plan(artifacts, dry_run=True)
print(preview.execution_summary)

# Applying without confirmation raises PermissionError for safety
try:
    engine.apply(preview, confirm=False)
except PermissionError as err:
    print(f"Blocked: {err}")

# Applying with explicit confirmation
result = engine.apply(preview, confirm=True, dry_run=True)
print(f"Apply result: {result.status}")
```

### 3. Using Reference Architecture Catalog

```python
from nexcoder_iac import ArchitectureCatalog, ArchitectureTier, IaCTarget

# Retrieve microservices specification for Hetzner Cloud
spec = ArchitectureCatalog.get(
    "microservices",
    target=IaCTarget.HETZNER,
    tier=ArchitectureTier.PRODUCTION,
)

artifacts = engine.generate(spec)
```

### 4. Running the Agentic Pipeline Workflow

```python
from nexcoder_iac import IaCTarget, run_iac_workflow

workflow_result = run_iac_workflow(
    description="Python web application with Redis and Postgres on AWS",
    target=IaCTarget.AWS,
    confirm_apply=False,
    dry_run=True,
)

print(workflow_result["plan_summary"])
print(f"Status: {workflow_result['apply_status']}")
```

---

## Command-Line Interface (CLI)

`nexcoder-iac` provides a command-line tool for developers:

```bash
# List catalog architectures
nexcoder-iac catalog list

# Inspect an architecture
nexcoder-iac catalog show app_database

# Generate Docker Compose stack locally
nexcoder-iac generate \
  --desc "Python app with Postgres and Redis" \
  --target local_compose \
  --out-dir ./infra-local

# Generate Terraform for Hetzner Cloud
nexcoder-iac generate \
  --desc "FastAPI with Postgres" \
  --target hetzner \
  --out-dir ./infra-hetzner

# Estimate monthly infrastructure costs
nexcoder-iac estimate \
  --arch microservices \
  --target aws \
  --tier production
```

---

## Applying Generated IaC with Your Credentials

Once templates are generated, you can inspect and apply them with standard CLI tooling:

### Local Target (Docker Compose)
```bash
cd ./infra-local
cp .env.example .env
docker compose up -d
```

### Cloud Targets (Terraform / OpenTofu)
```bash
cd ./infra-aws
cp .env.example .env
# Fill in your real credentials in .env or your shell session
export AWS_ACCESS_KEY_ID="your_real_key"
export AWS_SECRET_ACCESS_KEY="your_real_secret"

terraform init
terraform plan
terraform apply
```

### Dedicated VM Target (Ansible)
```bash
cd ./infra-vm
export SERVER_HOST="203.0.113.10"
export SSH_USER="ubuntu"
export SSH_PRIVATE_KEY_PATH="~/.ssh/id_rsa"

ansible-playbook -i inventory.ini playbook.yml
```
