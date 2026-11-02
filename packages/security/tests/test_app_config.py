from pathlib import Path

from faccoder_security.gate import (
    generate_csp_header,
    generate_security_md,
    pin_dependencies,
    scaffold_app_security,
)


def test_generate_csp_header():
    strict_csp = generate_csp_header(profile="strict")
    assert "default-src 'none'" in strict_csp
    assert "script-src 'self'" in strict_csp
    assert "frame-ancestors 'none'" in strict_csp

    spa_csp = generate_csp_header(profile="spa")
    assert "default-src 'self'" in spa_csp
    assert "font-src 'self'" in spa_csp

    api_csp = generate_csp_header(profile="api")
    assert "default-src 'none'" in api_csp
    assert "frame-ancestors 'none'" in api_csp


def test_generate_security_md():
    md = generate_security_md(project_name="DemoApp", contact_email="sec@demo.org")
    assert "# Security Policy" in md
    assert "DemoApp" in md
    assert "sec@demo.org" in md
    assert "Reporting a Vulnerability" in md


def test_pin_dependencies():
    unpinned = """
# Dependencies
requests>=2.28
pydantic
fastapi==0.111.0
httpx<=0.27
"""
    pinned = pin_dependencies(unpinned, default_fallback_version="1.0.0")
    assert "requests==2.28" in pinned
    assert "pydantic==1.0.0" in pinned
    assert "fastapi==0.111.0" in pinned
    assert "httpx==0.27" in pinned


def test_scaffold_app_security(tmp_path: Path):
    assets = scaffold_app_security(
        target_dir=tmp_path,
        project_name="MyTestService",
        contact_email="alerts@mytest.org",
    )
    sec_file = Path(assets["security_md"])
    assert sec_file.exists()
    assert "MyTestService" in sec_file.read_text(encoding="utf-8")
    assert "default-src 'none'" in assets["csp_header"]
