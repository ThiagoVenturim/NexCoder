"""Unit tests for server privatization and isolation auditor."""

from nexcoder_security.server.isolation import ServerIsolationAuditor


def test_audit_port_bindings_detects_exposed_internal_service():
    auditor = ServerIsolationAuditor()

    bindings = [
        {"port": 80, "host": "0.0.0.0", "service": "Nginx Web"},
        {"port": 443, "host": "0.0.0.0", "service": "Nginx TLS"},
        {"port": 22, "host": "0.0.0.0", "service": "SSH"},
        {"port": 5432, "host": "0.0.0.0", "service": "PostgreSQL"},
        {"port": 6379, "host": "127.0.0.1", "service": "Redis"},
    ]

    report = auditor.audit_port_bindings(bindings)
    assert report.passed is False
    assert report.total_violations == 1
    assert "PostgreSQL" in report.violations[0].target
    assert report.violations[0].severity == "critical"


def test_audit_port_bindings_clean_when_isolated():
    auditor = ServerIsolationAuditor()

    safe_bindings = [
        {"port": 80, "host": "0.0.0.0", "service": "Nginx Web"},
        {"port": 443, "host": "0.0.0.0", "service": "Nginx TLS"},
        {"port": 22, "host": "0.0.0.0", "service": "SSH"},
        {"port": 5432, "host": "127.0.0.1", "service": "PostgreSQL"},
        {"port": 6379, "host": "127.0.0.1", "service": "Redis"},
        {"port": 8000, "host": "127.0.0.1", "service": "App Upstream"},
    ]

    report = auditor.audit_port_bindings(safe_bindings)
    assert report.passed is True
    assert report.total_violations == 0


def test_audit_and_remediate_compose_text():
    raw_compose = """version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
  app:
    image: myapp:latest
    ports:
      - "8000:8000"
  db:
    image: postgres:16
    ports:
      - "5432:5432"
  cache:
    image: redis:7
    ports:
      - 6379:6379
"""

    auditor = ServerIsolationAuditor()
    report = auditor.audit_compose_text(raw_compose)
    assert report.passed is False
    # app (8000), db (5432), and cache (6379) are unshielded
    assert report.total_violations == 3

    remediated = auditor.remediate_compose_text(raw_compose)
    assert "127.0.0.1:8000:8000" in remediated
    assert "127.0.0.1:5432:5432" in remediated
    assert "127.0.0.1:6379:6379" in remediated
    # Public ports 80 and 443 remain untouched
    assert '"80:80"' in remediated
    assert '"443:443"' in remediated

    # Audit the remediated text: must now pass!
    report_after = auditor.audit_compose_text(remediated)
    assert report_after.passed is True
    assert report_after.total_violations == 0
