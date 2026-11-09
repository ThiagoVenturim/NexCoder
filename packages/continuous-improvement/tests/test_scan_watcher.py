"""Unit tests for security scan watcher and vulnerability diffing."""

from nexcoder_continuous_improvement.security.scan_watcher import (
    SecurityVulnerability,
    SecurityWatcher,
    Severity,
)


def test_security_watcher_detects_new_vulnerabilities() -> None:
    watcher = SecurityWatcher()

    baseline = [
        SecurityVulnerability(
            id="CVE-2025-1001",
            package="urllib3",
            installed_version="1.26.15",
            severity=Severity.LOW,
        )
    ]

    current = [
        SecurityVulnerability(
            id="CVE-2025-1001",
            package="urllib3",
            installed_version="1.26.15",
            severity=Severity.LOW,
        ),
        SecurityVulnerability(
            id="GHSA-crit-9999",
            package="fastapi",
            installed_version="0.100.0",
            fixed_version="0.110.0",
            severity=Severity.CRITICAL,
        ),
    ]

    diff = watcher.diff_scans(baseline, current, outdated_packages=["pydantic"])

    assert len(diff.new_vulnerabilities) == 1
    assert diff.new_vulnerabilities[0].id == "GHSA-crit-9999"
    assert not diff.resolved_vulnerabilities
    assert diff.critical_or_high_count == 1
    assert diff.requires_immediate_action is True
    assert "Immediate Action Required**: YES" in diff.summary_markdown
