"""Tests for credential isolation, safety verification, and secret scanning."""

from nexcoder_iac.catalog import ArchitectureCatalog
from nexcoder_iac.credentials import (
    generate_env_example,
    get_required_env_vars,
    scan_for_secrets,
    verify_user_credentials,
)
from nexcoder_iac.models import IaCTarget


def test_required_env_vars_per_target():
    assert get_required_env_vars(IaCTarget.LOCAL_COMPOSE) == []
    aws_vars = get_required_env_vars(IaCTarget.AWS)
    assert "AWS_ACCESS_KEY_ID" in aws_vars
    assert "AWS_SECRET_ACCESS_KEY" in aws_vars

    do_vars = get_required_env_vars(IaCTarget.DIGITALOCEAN)
    assert "DIGITALOCEAN_TOKEN" in do_vars

    hetzner_vars = get_required_env_vars(IaCTarget.HETZNER)
    assert "HCLOUD_TOKEN" in hetzner_vars


def test_verify_user_credentials_missing():
    ready, missing = verify_user_credentials(IaCTarget.AWS, env={})
    assert not ready
    assert "AWS_ACCESS_KEY_ID" in missing
    assert "AWS_SECRET_ACCESS_KEY" in missing


def test_verify_user_credentials_present():
    env = {
        "AWS_ACCESS_KEY_ID": "mock_id",
        "AWS_SECRET_ACCESS_KEY": "mock_secret",
        "AWS_REGION": "us-east-1",
    }
    ready, missing = verify_user_credentials(IaCTarget.AWS, env=env)
    assert ready
    assert len(missing) == 0


def test_scan_for_secrets_detects_violations():
    # Detects fake AWS key format
    clean = scan_for_secrets("resource aws_instance app { instance_type = var.type }")
    assert len(clean) == 0

    leaked_key = scan_for_secrets("aws_access_key = AKIAIOSFODNN7EXAMPLE")
    assert len(leaked_key) > 0
    assert any("AWS Access Key" in f for f in leaked_key)

    leaked_priv_key = scan_for_secrets("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...")
    assert len(leaked_priv_key) > 0
    assert any("Private Key" in f for f in leaked_priv_key)


def test_generate_env_example_safe():
    spec = ArchitectureCatalog.get("app_database", target=IaCTarget.AWS)
    env_content = generate_env_example(IaCTarget.AWS, spec)

    # Must contain placeholder variables
    assert "AWS_ACCESS_KEY_ID=your_aws_access_key_id_here" in env_content
    assert "DB_PASSWORD=your_secure_db_password_here" in env_content

    # Must not trigger secret scanner
    findings = scan_for_secrets(env_content)
    assert len(findings) == 0
