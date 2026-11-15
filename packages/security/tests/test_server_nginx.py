"""Unit tests for Nginx configuration generator and container validator."""

import subprocess

from nexcoder_security.server.nginx import (
    NginxConfigGenerator,
    validate_nginx_config_in_container,
    validate_nginx_config_syntax,
)


def test_nginx_generator_basic():
    gen = NginxConfigGenerator.basic(upstream="127.0.0.1:8000", domain="example.com")
    conf = gen.generate()

    assert "worker_processes auto;" in conf
    assert "events {" in conf
    assert "http {" in conf
    assert "upstream app_backend {" in conf
    assert "server 127.0.0.1:8000;" in conf
    assert "gzip on;" in conf
    assert "limit_req_zone $binary_remote_addr" in conf
    assert "Strict-Transport-Security" in conf
    assert "X-Frame-Options \"DENY\"" in conf
    assert "Content-Security-Policy" in conf
    assert "proxy_pass http://app_backend;" in conf

    # Validate syntax
    val = validate_nginx_config_syntax(conf)
    assert val.valid is True
    assert len(val.errors) == 0


def test_nginx_generator_advanced():
    gen = NginxConfigGenerator.advanced(
        domain="api.example.com",
        upstreams=["10.0.0.1:8000", "10.0.0.2:8000"],
        cert_path="/etc/ssl/certs/api.crt",
        key_path="/etc/ssl/private/api.key",
        strict_auth_rate_limit=True,
        client_max_body_size="50M",
        static_asset_path="/var/www/static",
    )
    conf = gen.generate()

    assert "server 10.0.0.1:8000;" in conf
    assert "server 10.0.0.2:8000;" in conf
    assert "ssl_certificate /etc/ssl/certs/api.crt;" in conf
    assert "ssl_certificate_key /etc/ssl/private/api.key;" in conf
    assert "client_max_body_size 50M;" in conf
    assert "location /healthz {" in conf
    assert "location /static/ {" in conf
    assert "location /api/auth/ {" in conf
    assert "limit_req zone=auth_limit" in conf

    val = validate_nginx_config_syntax(conf)
    assert val.valid is True


def test_nginx_syntax_validation_catches_errors():
    # Missing semicolon
    broken_conf = "server {\n    listen 80\n    server_name localhost;\n}"
    val = validate_nginx_config_syntax(broken_conf)
    assert val.valid is False
    assert any("must terminate with ';'" in e for e in val.errors)

    # Unclosed brace
    unclosed_conf = "events {\n    worker_connections 1024;\n\nhttp {\n    server {\n        listen 80;\n    }\n"
    val2 = validate_nginx_config_syntax(unclosed_conf)
    assert val2.valid is False
    assert any("unclosed brace" in e for e in val2.errors)


def test_nginx_container_validation_simulated():
    gen = NginxConfigGenerator.basic(upstream="127.0.0.1:8000", domain="test.local")
    conf = gen.generate()

    executed_cmds: list[list[str]] = []

    def mock_container_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        executed_cmds.append(cmd)
        out_msg = (
            "nginx: the configuration file /tmp/test_nginx.conf syntax is ok\n"
            "nginx: configuration file /tmp/test_nginx.conf test is successful"
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=out_msg,
            stderr="",
        )

    val = validate_nginx_config_in_container(conf, container_runner=mock_container_runner)
    assert val.valid is True
    assert val.executed_in_container is True
    assert "syntax is ok" in val.details
    assert len(executed_cmds) == 1
    assert "docker" in executed_cmds[0][0]
    assert "nginx -t" in executed_cmds[0][-1]


def test_nginx_container_validation_failure():
    conf = "server { listen 80; }"

    def mock_failed_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="nginx: [emerg] invalid directive in /tmp/test_nginx.conf:1",
        )

    val = validate_nginx_config_in_container(conf, container_runner=mock_failed_runner)
    assert val.valid is False
    assert val.executed_in_container is True
    assert len(val.errors) > 0
