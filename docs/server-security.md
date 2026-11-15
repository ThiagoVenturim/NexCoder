# Server Security: Nginx, Hardening, Privatization, and Data Masking

Comprehensive guide for configuring secure application exposure, operating system hardening, network privatization, and data masking across the NexCoder platform.

## Architecture and Threat Model

Exposing an application securely requires defense in depth across the networking, host operating system, and data storage layers:

```
                          [ Public Internet ]
                                   |
                          [ Firewall: 80, 443 ]
                                   |
                  +--------------------------------+
                  |     Hardened Nginx Ingress     |
                  |  - TLS 1.2/1.3 + HSTS          |
                  |  - Security Headers (CSP/CORS) |
                  |  - Rate Limiting (IP / Auth)   |
                  |  - Gzip Compression            |
                  |  - Drop direct server tokens   |
                  +--------------------------------+
                                   |
                      [ 127.0.0.1 / Private Bridge ]
                                   |
      +----------------------------+----------------------------+
      |                                                         |
[ Web App (8000) ]                                     [ Database / Cache ]
  - Non-root user                                        - Bound to 127.0.0.1
  - Masked logs (PII removed)                            - Chmod 0600 secrets
  - Private network only                                 - No public port exposed
```

## 1. Nginx Reverse Proxy and TLS

`NginxConfigGenerator` produces production-ready, security-hardened Nginx configurations with:

- **Profiles**:
  - `basic`: Single-command secure reverse proxy for standard single-upstream web applications.
  - `advanced`: Multi-upstream load balancing (`round_robin`, `least_conn`, `ip_hash`), custom certificate paths, dedicated strict rate limiting on auth endpoints (`/api/auth/`), static asset caching, and healthcheck endpoints.
- **TLS Hardening**: Modern TLS 1.2 and 1.3 only, high-entropy cipher suites, session ticket disabling, and Let's Encrypt / Certbot renewal ACME challenge webroots.
- **Security Headers**: HSTS (`max-age=31536000; includeSubDomains; preload`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and strict Content Security Policy (`CSP`).
- **Rate Limiting**: Configurable `limit_req_zone` per binary client IP address with burst and nodelay.
- **Validation**: Full syntax parser checking directive termination and balanced blocks, plus container-based validation (`nginx -t`).

### Usage Example

```python
from nexcoder_security.server import NginxConfigGenerator, validate_nginx_config_syntax

# Basic profile
gen = NginxConfigGenerator.basic(upstream="127.0.0.1:8000", domain="app.example.com")
conf = gen.generate()

# Advanced profile
adv_gen = NginxConfigGenerator.advanced(
    domain="api.example.com",
    upstreams=["10.0.0.1:8000", "10.0.0.2:8000"],
    cert_path="/etc/letsencrypt/live/api.example.com/fullchain.pem",
    key_path="/etc/letsencrypt/live/api.example.com/privkey.pem",
    strict_auth_rate_limit=True,
    client_max_body_size="50M",
    static_asset_path="/var/www/static",
)
adv_conf = adv_gen.generate()

# Validate
result = validate_nginx_config_syntax(adv_conf)
assert result.valid is True
```

## 2. Server Hardening Scripts and Idempotent Checklist

Hardening scripts configure the underlying host OS adhering to the principle of least privilege:

- **Firewall**: Default deny incoming traffic, allowing only necessary ingress (SSH, HTTP 80, HTTPS 443). Supports `ufw` and `nftables` on Linux, and `NetSecurity` / `New-NetFirewallRule` on Windows Server.
- **SSH Hardening**: Disables password authentication, disables root login (`PermitRootLogin no`), enforces public keys, sets idle connection timeout (`ClientAliveInterval 300`), and limits authentication retries.
- **Intrusion Prevention**: Deploys `fail2ban` jail configuration (`jail.local`) banning repeated authentication failures.
- **Automatic Security Updates**: Activates `unattended-upgrades` periodic job for Debian/Ubuntu.
- **Non-Root Service Account**: Provisions dedicated unprivileged system service user (`nexcoder`) with restricted shell and umask `027`.
- **Kernel Hardening (sysctl)**: Enables TCP SYN cookies, disables IP forwarding, disables ICMP redirects, enforces protected symlinks/hardlinks, and turns on address space layout randomization (`ASLR`).
- **Idempotence**: Both the generated scripts and the `ServerHardeningEngine` are strictly idempotent. Re-running the hardening process leaves zero configuration changes and passes all checklist items.

### Usage Example

```python
from nexcoder_security.server import (
    HardeningOptions,
    ServerHardeningEngine,
    generate_bash_hardening_script,
    generate_ps1_hardening_script,
)

opts = HardeningOptions(profile="basic", os_target="linux")
bash_script = generate_bash_hardening_script(opts)
ps1_script = generate_ps1_hardening_script(opts)

# Programmatic checklist audit and idempotent execution
engine = ServerHardeningEngine(opts)
initial_state = {"permit_root_login": True, "password_authentication": True}
state_after_first, res_first = engine.apply_checklist(initial_state)
assert res_first.changes_made > 0

# Second pass produces 0 changes
state_after_second, res_second = engine.apply_checklist(state_after_first)
assert res_second.changes_made == 0
```

## 3. Privatization and Network Isolation

The isolation engine guarantees that internal storage engines and microservices are never exposed to the public internet:

- **Port Binding Audit**: Scans active listening sockets and verifies that databases (PostgreSQL 5432, MySQL 3306, MongoDB 27017, Redis 6379) and upstream app ports are bound exclusively to `127.0.0.1` or internal Docker networks.
- **Docker Compose Remediation**: Automatically identifies unshielded port mappings (e.g., `- "5432:5432"`) and remediates them to private loopback mappings (e.g., `- "127.0.0.1:5432:5432"`).
- **Secret File Permissions**: Checks file permissions on secret configurations (`.env`) ensuring modes are restricted (`chmod 0600` or `0400`).

### Usage Example

```python
from nexcoder_security.server import ServerIsolationAuditor

auditor = ServerIsolationAuditor()

compose_text = """
services:
  db:
    image: postgres:16
    ports:
      - "5432:5432"
"""

report = auditor.audit_compose_text(compose_text)
assert not report.passed

remediated = auditor.remediate_compose_text(compose_text)
assert '127.0.0.1:5432:5432' in remediated
```

## 4. PII and Sensitive Data Masking

The `DataMasker` anonymizes sensitive personal information and secrets across text logs, SQL dumps, structured JSON, and CSV tables:

- **Entities Masked**: Email addresses, Brazilian CPFs, CNPJs, phone numbers, credit card numbers, IPv4 addresses, API keys / bearer tokens, and credentials in connection URIs.
- **Strategies**:
  - `placeholder`: Deterministic token replacement (e.g., `[EMAIL_1]`, `[CPF_1]`) supporting session unmasking.
  - `redact`: Static redaction (e.g., `***@domain.com`, `[CARD_REDACTED]`).
  - `hash`: Cryptographic salted HMAC/SHA-256 for consistent tokenization across distributed test datasets without exposing plaintext.
- **SQL Dumps**: Preserves valid SQL syntax while masking literals inside `INSERT INTO` statements.

### Usage Example

```python
from nexcoder_security.server import DataMasker

masker = DataMasker.basic()

# Mask log lines
masked_log = masker.mask_log_file("User user@example.com connected from 192.168.1.10")

# Mask SQL dump
sql_dump = "INSERT INTO users (email, cpf) VALUES ('test@corp.com', '123.456.789-00');"
masked_sql = masker.mask_sql_dump(sql_dump)

# Mask structured JSON
data = {"user": "bob", "email": "bob@example.com", "secret_key": "vault_secret_token_placeholder"}
masked_data = masker.mask_record(data)
```

## 5. CLI Commands

`nexcoder-security server` provides unified terminal commands for all operations:

```bash
# Generate basic Nginx configuration
nexcoder-security server nginx --domain app.example.com --upstream 127.0.0.1:8000 --output nginx.conf --owned-target

# Generate advanced Nginx configuration and validate syntax
nexcoder-security server nginx --profile advanced --domain api.example.com --upstream 127.0.0.1:8000 --validate-container --owned-target

# Generate OS hardening scripts for Linux (bash) and Windows (ps1)
nexcoder-security server hardening --profile basic --output-bash hardening.sh --output-ps1 hardening.ps1 --owned-target

# Audit and remediate Docker Compose port exposure
nexcoder-security server isolate ./docker-compose.yml --remediate --owned-target

# Mask sensitive PII in SQL database dump
nexcoder-security server mask ./backup.sql --format sql --strategy placeholder --output ./backup_masked.sql --owned-target
```
