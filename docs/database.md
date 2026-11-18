# Pluggable Database Architecture

NexCoder provides a pluggable database architecture that allows teams to use SQLite by default with zero configuration, or connect to external relational databases (PostgreSQL, MySQL, Microsoft SQL Server) via standard SQLAlchemy URLs and ODBC drivers.

## Overview

Storage in NexCoder is divided into two primary subsystems:
1. **Core Storage (`nexcoder-core`)**: Hybrid retrieval index (`HybridStore`), chunk vectors, and semantic cache (`SemanticCache`).
2. **Control Plane (`nexcoder-control`)**: Append-only cryptographic audit logs (`AppendOnlyAuditLog`) and API key management (`APIKeyService`, `SQLAlchemyAPIKeyStore`).

Both subsystems share a unified schema abstraction and adhere to:
- **Zero Configuration Default**: Uses local SQLite (`.nexcoder/nexcoder.db` and `.nexcoder/index.sqlite`) when no `DB_URL` is configured.
- **Pluggable URL Engine**: Configurable via the `DB_URL` (or `NEXCODER_DB_URL`) environment variable.
- **Strict Parameterization**: All SQL queries use SQLAlchemy Core expressions and bind parameters, preventing SQL injection vulnerabilities.
- **Dialect Compatibility**: Schemas and types map cleanly across SQLite, PostgreSQL, MySQL, and Microsoft SQL Server.

## Database URL Specification

Configure the database connection using the `DB_URL` environment variable:

### 1. SQLite (Default)
Local file or in-memory database:
```bash
# In-memory database (useful for ephemeral testing)
DB_URL="sqlite:///:memory:"

# Explicit file path
DB_URL="sqlite:///./data/nexcoder.db"
```

### 2. PostgreSQL
Using `psycopg` (v3) or `psycopg2`:
```bash
# psycopg v3 (recommended)
DB_URL="postgresql+psycopg://username:password@localhost:5432/nexcoder"

# psycopg2
DB_URL="postgresql+psycopg2://username:password@localhost:5432/nexcoder"
```
Install optional dependencies:
```bash
pip install -e "packages/core[postgres]"
```

### 3. MySQL / MariaDB
Using `pymysql`:
```bash
DB_URL="mysql+pymysql://username:password@localhost:3306/nexcoder"
```
Install optional dependencies:
```bash
pip install -e "packages/core[mysql]"
```

### 4. Microsoft SQL Server & ODBC
Using `pyodbc` with connection URL or raw ODBC connection string:
```bash
# Standard SQLAlchemy URL with pyodbc
DB_URL="mssql+pyodbc://username:password@sqlserver.example.internal:1433/nexcoder?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

# Raw ODBC Connection String (automatically normalized by NexCoder)
DB_URL="Driver={ODBC Driver 18 for SQL Server};Server=tcp:sqlserver.example.internal,1433;Database=nexcoder;Uid=username;Pwd=password;Encrypt=yes;TrustServerCertificate=no;"
```
Install optional dependencies:
```bash
pip install -e "packages/core[mssql]"
```

## Security and Secrets Policy

1. Never commit real credentials, passwords, or connection strings into version control.
2. Store database credentials in a local `.env` file (which is excluded from Git via `.gitignore`).
3. For deployment environments, inject `DB_URL` through container environment variables or Kubernetes Secrets.

## Running with Containers

### Docker Compose
Run the application and PostgreSQL database with Docker Compose:
```bash
docker compose up --build
```

This starts:
- `db`: PostgreSQL 16 container with persistent volume storage.
- `app`: NexCoder multiplatform container connected to PostgreSQL via `DB_URL`.

To stop the services:
```bash
docker compose down
```

### Kubernetes
Deploy NexCoder manifests into your Kubernetes cluster:
```bash
# 1. Apply configuration and secrets
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml.example

# 2. Deploy optional in-cluster database
kubectl apply -f k8s/postgres.yaml

# 3. Deploy NexCoder application and service
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## Multiplatform Execution Scripts

NexCoder provides equivalent execution scripts for Windows and POSIX systems (Linux/macOS):

### Windows (PowerShell)
```powershell
# Run locally with default SQLite
.\scripts\run.ps1 -Mode local

# Run with custom DB_URL
.\scripts\run.ps1 -Mode local -DbUrl "postgresql+psycopg2://usr:pwd@localhost:5432/mydb"

# Run via Docker Compose
.\scripts\run.ps1 -Mode docker

# Run offline verification tests
.\scripts\run.ps1 -Mode test
```

### Linux / macOS (Bash)
```bash
# Run locally with default SQLite
./scripts/run.sh local

# Run with custom DB_URL
DB_URL="postgresql+psycopg2://usr:pwd@localhost:5432/mydb" ./scripts/run.sh local

# Run via Docker Compose
./scripts/run.sh docker

# Run offline verification tests
./scripts/run.sh test
```

## Multiplatform Architecture & Mobile Access

NexCoder backend services are cross-platform and execute identically on Linux, macOS, and Windows. Where user interfaces exist (such as the control panel and web dashboards), mobile access (Android / iOS) is provided via Progressive Web App (PWA) standards without requiring proprietary mobile native builds.
