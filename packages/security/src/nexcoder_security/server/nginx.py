"""Nginx reverse proxy and TLS configuration generator with security hardening."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nexcoder_security.gate.app_config import generate_csp_header

NginxProfile = Literal["basic", "advanced"]


class NginxOptions(BaseModel):
    """Configuration options for Nginx reverse proxy generation."""

    profile: NginxProfile = "basic"
    domain: str = "localhost"
    server_name: str = "localhost"
    http_port: int = 80
    https_port: int = 443
    enable_tls: bool = True
    force_https_redirect: bool = True
    cert_path: str | None = None
    key_path: str | None = None
    certbot_support: bool = True

    upstream_name: str = "app_backend"
    upstream_servers: list[str] = Field(default_factory=lambda: ["127.0.0.1:8000"])
    upstream_strategy: Literal["round_robin", "least_conn", "ip_hash"] = "round_robin"

    enable_gzip: bool = True
    gzip_comp_level: int = 6
    gzip_types: list[str] = Field(
        default_factory=lambda: [
            "text/plain",
            "text/css",
            "application/json",
            "application/javascript",
            "text/xml",
            "application/xml",
            "application/xml+rss",
            "text/javascript",
            "image/svg+xml",
        ]
    )

    enable_rate_limiting: bool = True
    rate_limit_zone_name: str = "req_limit_per_ip"
    rate_limit_zone_size: str = "10m"
    rate_limit_rate: str = "10r/s"
    rate_limit_burst: int = 20
    rate_limit_nodelay: bool = True
    rate_limit_status: int = 429

    strict_auth_rate_limit: bool = False
    auth_rate_limit_rate: str = "3r/s"
    auth_rate_limit_burst: int = 5
    auth_path_prefix: str = "/api/auth/"

    client_max_body_size: str = "10M"
    server_tokens: bool = False

    csp_profile: Literal["strict", "spa", "api"] = "strict"
    custom_csp: str | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)

    enable_websocket: bool = True
    enable_health_check: bool = True
    health_check_path: str = "/healthz"

    static_asset_path: str | None = None
    static_location_prefix: str = "/static/"

    proxy_connect_timeout: int = 60
    proxy_read_timeout: int = 60
    proxy_send_timeout: int = 60

    as_full_conf: bool = True
    worker_processes: str = "auto"
    worker_connections: int = 1024


class NginxValidationResult(BaseModel):
    """Result of Nginx configuration validation."""

    valid: bool
    executed_in_container: bool = False
    details: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NginxConfigGenerator:
    """Generates hardened Nginx reverse proxy configurations."""

    def __init__(self, options: NginxOptions | None = None) -> None:
        self.options = options or NginxOptions()

    @classmethod
    def basic(
        cls,
        upstream: str = "127.0.0.1:8000",
        domain: str = "localhost",
        enable_tls: bool = True,
    ) -> NginxConfigGenerator:
        """Create generator with secure basic defaults."""
        opts = NginxOptions(
            profile="basic",
            domain=domain,
            server_name=domain,
            upstream_servers=[upstream],
            enable_tls=enable_tls,
            client_max_body_size="10M",
            enable_rate_limiting=True,
            enable_gzip=True,
        )
        return cls(opts)

    @classmethod
    def advanced(
        cls,
        domain: str,
        upstreams: list[str],
        cert_path: str | None = None,
        key_path: str | None = None,
        strict_auth_rate_limit: bool = True,
        client_max_body_size: str = "50M",
        static_asset_path: str | None = None,
    ) -> NginxConfigGenerator:
        """Create generator with advanced multi-upstream, strict rate limit and caching."""
        opts = NginxOptions(
            profile="advanced",
            domain=domain,
            server_name=domain,
            upstream_servers=upstreams,
            enable_tls=True,
            cert_path=cert_path,
            key_path=key_path,
            strict_auth_rate_limit=strict_auth_rate_limit,
            client_max_body_size=client_max_body_size,
            static_asset_path=static_asset_path,
            enable_health_check=True,
            enable_rate_limiting=True,
            enable_gzip=True,
        )
        return cls(opts)

    def generate(self, options: NginxOptions | None = None) -> str:
        """Generate the Nginx configuration string."""
        opts = options or self.options
        if opts.as_full_conf:
            return self._generate_full_conf(opts)
        return self._generate_server_blocks(opts)

    def _build_security_headers(self, opts: NginxOptions) -> list[str]:
        headers: list[str] = []

        # HSTS only valid over TLS
        if opts.enable_tls:
            hsts_val = "max-age=31536000; includeSubDomains; preload"
            headers.append(f'add_header Strict-Transport-Security "{hsts_val}" always;')

        headers.append('add_header X-Content-Type-Options "nosniff" always;')
        headers.append('add_header X-Frame-Options "DENY" always;')
        headers.append('add_header X-XSS-Protection "0" always;')
        headers.append('add_header Referrer-Policy "strict-origin-when-cross-origin" always;')
        headers.append('add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;')

        csp_val = opts.custom_csp or generate_csp_header(profile=opts.csp_profile)
        # Escape quotes in CSP for nginx add_header
        clean_csp = csp_val.replace('"', '\\"')
        headers.append(f'add_header Content-Security-Policy "{clean_csp}" always;')

        for k, v in opts.custom_headers.items():
            headers.append(f'add_header {k} "{v}" always;')

        return headers

    def _generate_server_blocks(self, opts: NginxOptions) -> str:
        blocks: list[str] = []

        cert_file = opts.cert_path or f"/etc/letsencrypt/live/{opts.domain}/fullchain.pem"
        key_file = opts.key_path or f"/etc/letsencrypt/live/{opts.domain}/privkey.pem"

        # HTTP block: Redirect to HTTPS or serve direct HTTP
        if opts.enable_tls and opts.force_https_redirect:
            http_lines = [
                "server {",
                f"    listen {opts.http_port};",
                f"    listen [::]:{opts.http_port};",
                f"    server_name {opts.server_name};",
                "    server_tokens off;",
            ]
            if opts.certbot_support:
                http_lines.extend(
                    [
                        "",
                        "    location /.well-known/acme-challenge/ {",
                        "        root /var/www/certbot;",
                        "        allow all;",
                        "    }",
                    ]
                )
            http_lines.extend(
                [
                    "",
                    "    location / {",
                    f"        return 301 https://$host:{opts.https_port}$request_uri;"
                    if opts.https_port != 443
                    else "        return 301 https://$host$request_uri;",
                    "    }",
                    "}",
                ]
            )
            blocks.append("\n".join(http_lines))

        # Main Server block (HTTPS if enable_tls, else HTTP)
        main_listen_port = opts.https_port if opts.enable_tls else opts.http_port
        main_lines = [
            "server {",
            f"    listen {main_listen_port}{' ssl' if opts.enable_tls else ''};",
            f"    listen [::]:{main_listen_port}{' ssl' if opts.enable_tls else ''};",
            f"    server_name {opts.server_name};",
            f"    server_tokens {'on' if opts.server_tokens else 'off'};",
            f"    client_max_body_size {opts.client_max_body_size};",
        ]

        # TLS configuration
        if opts.enable_tls:
            main_lines.extend(
                [
                    "",
                    f"    ssl_certificate {cert_file};",
                    f"    ssl_certificate_key {key_file};",
                    "    ssl_protocols TLSv1.2 TLSv1.3;",
                    "    ssl_ciphers HIGH:!aNULL:!MD5;",
                    "    ssl_prefer_server_ciphers on;",
                    "    ssl_session_cache shared:SSL:10m;",
                    "    ssl_session_timeout 1d;",
                    "    ssl_session_tickets off;",
                ]
            )

        # Security headers
        main_lines.append("")
        for header in self._build_security_headers(opts):
            main_lines.append(f"    {header}")

        # Healthcheck location
        if opts.enable_health_check:
            main_lines.extend(
                [
                    "",
                    f"    location {opts.health_check_path} {{",
                    "        access_log off;",
                    '        return 200 "healthy\\n";',
                    "    }",
                ]
            )

        # Static assets location
        if opts.static_asset_path:
            main_lines.extend(
                [
                    "",
                    f"    location {opts.static_location_prefix} {{",
                    f"        alias {opts.static_asset_path};",
                    "        expires 30d;",
                    '        add_header Cache-Control "public, no-transform";',
                    "    }",
                ]
            )

        # Strict auth rate limiting location (advanced profile)
        if opts.strict_auth_rate_limit and opts.enable_rate_limiting:
            main_lines.extend(
                [
                    "",
                    f"    location {opts.auth_path_prefix} {{",
                    "        limit_req zone=auth_limit burst="
                    + str(opts.auth_rate_limit_burst)
                    + " nodelay;",
                    "        proxy_pass http://" + opts.upstream_name + ";",
                    "        proxy_http_version 1.1;",
                    "        proxy_set_header Host $host;",
                    "        proxy_set_header X-Real-IP $remote_addr;",
                    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                    "        proxy_set_header X-Forwarded-Proto $scheme;",
                    "    }",
                ]
            )

        # Root reverse proxy location
        root_loc = [
            "",
            "    location / {",
        ]
        if opts.enable_rate_limiting:
            nodelay_flag = " nodelay" if opts.rate_limit_nodelay else ""
            root_loc.append(
                f"        limit_req zone={opts.rate_limit_zone_name} burst={opts.rate_limit_burst}{nodelay_flag};"
            )

        root_loc.extend(
            [
                f"        proxy_pass http://{opts.upstream_name};",
                "        proxy_http_version 1.1;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto $scheme;",
                f"        proxy_connect_timeout {opts.proxy_connect_timeout}s;",
                f"        proxy_read_timeout {opts.proxy_read_timeout}s;",
                f"        proxy_send_timeout {opts.proxy_send_timeout}s;",
            ]
        )

        if opts.enable_websocket:
            root_loc.extend(
                [
                    "        proxy_set_header Upgrade $http_upgrade;",
                    "        proxy_set_header Connection $connection_upgrade;",
                ]
            )

        root_loc.append("    }")
        main_lines.extend(root_loc)
        main_lines.append("}")
        blocks.append("\n".join(main_lines))

        return "\n\n".join(blocks)

    def _generate_full_conf(self, opts: NginxOptions) -> str:
        lines: list[str] = [
            f"worker_processes {opts.worker_processes};",
            "pid /tmp/nginx.pid;",
            "",
            "events {",
            f"    worker_connections {opts.worker_connections};",
            "}",
            "",
            "http {",
            "    include /etc/nginx/mime.types;",
            "    default_type application/octet-stream;",
            "    sendfile on;",
            "    tcp_nopush on;",
            "    tcp_nodelay on;",
            "    keepalive_timeout 65;",
            "    server_tokens off;",
            "",
        ]

        # Gzip configuration
        if opts.enable_gzip:
            gzip_types_str = " ".join(opts.gzip_types)
            lines.extend(
                [
                    "    gzip on;",
                    "    gzip_vary on;",
                    "    gzip_proxied any;",
                    f"    gzip_comp_level {opts.gzip_comp_level};",
                    f"    gzip_types {gzip_types_str};",
                    "",
                ]
            )

        # Rate limiting zones
        if opts.enable_rate_limiting:
            rate_zone = (
                f"    limit_req_zone $binary_remote_addr "
                f"zone={opts.rate_limit_zone_name}:{opts.rate_limit_zone_size} rate={opts.rate_limit_rate};"
            )
            lines.extend(
                [
                    rate_zone,
                    f"    limit_req_status {opts.rate_limit_status};",
                ]
            )
            if opts.strict_auth_rate_limit:
                lines.append(
                    f"    limit_req_zone $binary_remote_addr zone=auth_limit:10m rate={opts.auth_rate_limit_rate};"
                )
            lines.append("")

        # Connection upgrade map for WebSockets
        if opts.enable_websocket:
            lines.extend(
                [
                    "    map $http_upgrade $connection_upgrade {",
                    "        default upgrade;",
                    "        ''      close;",
                    "    }",
                    "",
                ]
            )

        # Upstream block
        lines.append(f"    upstream {opts.upstream_name} {{")
        if opts.upstream_strategy == "least_conn":
            lines.append("        least_conn;")
        elif opts.upstream_strategy == "ip_hash":
            lines.append("        ip_hash;")
        for srv in opts.upstream_servers:
            lines.append(f"        server {srv};")
        lines.append("    }")
        lines.append("")

        # Indent server blocks inside http {}
        server_blocks = self._generate_server_blocks(opts)
        indented = "\n".join(["    " + line if line.strip() else "" for line in server_blocks.splitlines()])
        lines.append(indented)
        lines.append("}")
        lines.append("")

        return "\n".join(lines)


def validate_nginx_config_syntax(config: str) -> NginxValidationResult:
    """Validate Nginx configuration syntax, block nesting, and directive termination."""
    errors: list[str] = []
    warnings: list[str] = []

    lines = config.splitlines()
    brace_depth = 0

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        opens = line.count("{")
        closes = line.count("}")
        brace_depth += opens - closes

        if brace_depth < 0:
            errors.append(f"Line {idx}: Unmatched closing brace '}}'")
            brace_depth = 0

        # In Nginx syntax:
        # Every statement must either open a block (end with '{'),
        # close a block (end with '}'), or terminate with ';'
        if line.endswith("{"):
            pass
        elif line.endswith("}") or line.endswith("};"):
            pass
        else:
            if not line.endswith(";"):
                errors.append(f"Line {idx}: Directive '{line}' must terminate with ';'")

    if brace_depth != 0:
        errors.append(f"Configuration has {brace_depth} unclosed brace(s)")

    has_server = re.search(r"\bserver\s*\{", config) is not None
    if not has_server:
        errors.append("Configuration missing 'server' block")

    valid = len(errors) == 0
    return NginxValidationResult(
        valid=valid,
        executed_in_container=False,
        details="Syntax check passed" if valid else f"Syntax errors: {'; '.join(errors)}",
        errors=errors,
        warnings=warnings,
    )


def validate_nginx_config_in_container(
    config: str,
    image: str = "nginx:alpine",
    docker_executable: str = "docker",
    container_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> NginxValidationResult:
    """Validate Nginx configuration using 'nginx -t' in a container.

    Falls back cleanly to offline syntax validation if docker daemon is not available.
    """
    syntax_res = validate_nginx_config_syntax(config)
    if not syntax_res.valid:
        return syntax_res

    runner = container_runner
    if runner is None:
        docker_bin = shutil.which(docker_executable)
        if not docker_bin:
            syntax_res.warnings.append("docker binary not found; validated via structural syntax parser")
            return syntax_res

        # Test if docker daemon is running
        try:
            check_daemon = subprocess.run(  # noqa: S603
                [docker_bin, "info"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if check_daemon.returncode != 0:
                syntax_res.warnings.append("docker daemon not running; validated via structural syntax parser")
                return syntax_res
        except Exception:
            syntax_res.warnings.append("docker check timed out; validated via structural syntax parser")
            return syntax_res

        def default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)  # noqa: S603

        runner = default_runner

    # Write config to temporary file for container mount
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8") as tmp:
        tmp.write(config)
        tmp_path = Path(tmp.name)

    try:
        # Create self-signed dummy certs if SSL is referenced so nginx -t doesn't fail on missing cert file
        test_script = (
            "mkdir -p /etc/letsencrypt/live/localhost /etc/letsencrypt/live/example.com /var/www/certbot && "
            "openssl req -x509 -nodes -days 1 -newkey rsa:2048 "
            "-keyout /etc/letsencrypt/live/localhost/privkey.pem "
            "-out /etc/letsencrypt/live/localhost/fullchain.pem "
            '-subj "/CN=localhost" 2>/dev/null || true; '
            "openssl req -x509 -nodes -days 1 -newkey rsa:2048 "
            "-keyout /etc/letsencrypt/live/example.com/privkey.pem "
            "-out /etc/letsencrypt/live/example.com/fullchain.pem "
            '-subj "/CN=example.com" 2>/dev/null || true; '
            "nginx -t -c /tmp/test_nginx.conf"
        )

        cmd = [
            docker_executable,
            "run",
            "--rm",
            "-v",
            f"{tmp_path.resolve()}:/tmp/test_nginx.conf:ro",
            "--entrypoint",
            "sh",
            image,
            "-c",
            test_script,
        ]

        proc = runner(cmd)
        combined_output = (proc.stdout + "\n" + proc.stderr).strip()

        if proc.returncode == 0 and "syntax is ok" in combined_output.lower():
            return NginxValidationResult(
                valid=True,
                executed_in_container=True,
                details=combined_output,
                errors=[],
                warnings=[],
            )
        else:
            return NginxValidationResult(
                valid=False,
                executed_in_container=True,
                details=combined_output,
                errors=[combined_output],
                warnings=[],
            )
    except Exception as exc:
        syntax_res.warnings.append(f"Container validation failed ({exc}); validated via structural syntax parser")
        return syntax_res
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
