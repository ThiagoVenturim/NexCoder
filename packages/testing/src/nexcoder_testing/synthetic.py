"""Synthetic user application fixture for offline extreme testing verification."""

from __future__ import annotations

import contextlib
import http.server
import json
import socketserver
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nexcoder_testing.models import APIEndpointSpec, DOMScreenSpec, SystemFlowSpec

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]


LOGIN_SCREEN_HTML_FLAWED = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Sign In - Synthetic App</title>
</head>
<body>
    <header>
        <img src="/static/brand.png" />
        <h1>Welcome to Synthetic App</h1>
    </header>
    <main>
        <form id="login-form" action="/login" method="post">
            <label for="email">Email Address</label>
            <input id="email" name="email" type="email" data-testid="login-email" />
            <label for="password">Password</label>
            <input id="password" name="password" type="password" data-testid="login-password" />
            <button id="submit-login" type="submit" data-testid="login-submit">Sign In</button>
        </form>
    </main>
</body>
</html>
"""

LOGIN_SCREEN_HTML_CLEAN = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Sign In - Synthetic App</title>
</head>
<body>
    <header>
        <img src="/static/brand.png" alt="Synthetic App Logo" />
        <h1>Welcome to Synthetic App</h1>
    </header>
    <main>
        <form id="login-form" action="/login" method="post">
            <label for="email">Email Address</label>
            <input id="email" name="email" type="email" data-testid="login-email" aria-label="Email Address" />
            <label for="password">Password</label>
            <input id="password" name="password" type="password" data-testid="login-password" aria-label="Password" />
            <button id="submit-login" type="submit" data-testid="login-submit">Sign In</button>
        </form>
    </main>
</body>
</html>
"""

DASHBOARD_SCREEN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Orders Dashboard</title>
</head>
<body>
    <main>
        <h1>Orders Dashboard</h1>
        <p>Active customer orders and inventory status.</p>
        <input id="search-orders" name="search" type="search" data-testid="orders-search" aria-label="Search orders" />
        <button id="new-order-btn" type="button" data-testid="new-order-btn">Create Order</button>
        <a id="items-link" href="/api/items" data-testid="items-link">View Catalog</a>
    </main>
</body>
</html>
"""

CONTRACTS_PY_FLAWED = '''"""Business contracts and domain calculations for the synthetic application."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderItemContract:
    item_id: str
    unit_price: float
    quantity: int


def calculate_order_total(unit_price: float, quantity: int, discount_pct: float = 0.0) -> float:
    """Calculate total order amount after percentage discount."""
    if unit_price < 0:
        raise ValueError("unit_price cannot be negative")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError("discount_pct must be between 0 and 100")
    subtotal = unit_price * quantity
    return round(subtotal * (1.0 - (discount_pct / 100.0)), 2)


def compute_page_count(total_items: int, page_size: int) -> int:
    """Compute number of pages for a paginated query.

    Intentional boundary defect when include_flaws=True: does not guard page_size <= 0,
    causing ZeroDivisionError when page_size == 0.
    """
    return (total_items + page_size - 1) // page_size


def normalize_sku(sku: str) -> str:
    """Normalize SKU identifier to uppercase alphanumeric."""
    cleaned = sku.strip().upper()
    if not cleaned:
        raise ValueError("sku cannot be empty")
    return cleaned
'''

CONTRACTS_PY_CLEAN = '''"""Business contracts and domain calculations for the synthetic application."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderItemContract:
    item_id: str
    unit_price: float
    quantity: int


def calculate_order_total(unit_price: float, quantity: int, discount_pct: float = 0.0) -> float:
    """Calculate total order amount after percentage discount."""
    if unit_price < 0:
        raise ValueError("unit_price cannot be negative")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError("discount_pct must be between 0 and 100")
    subtotal = unit_price * quantity
    return round(subtotal * (1.0 - (discount_pct / 100.0)), 2)


def compute_page_count(total_items: int, page_size: int) -> int:
    """Compute number of pages for a paginated query."""
    if total_items < 0:
        raise ValueError("total_items cannot be negative")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    return (total_items + page_size - 1) // page_size


def normalize_sku(sku: str) -> str:
    """Normalize SKU identifier to uppercase alphanumeric."""
    cleaned = sku.strip().upper()
    if not cleaned:
        raise ValueError("sku cannot be empty")
    return cleaned
'''

CLI_PROCESS_PY = '''"""Command-line process entrypoint for the synthetic application."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synthetic-app")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--workflow", choices=["checkout", "inventory"], default=None)
    args = parser.parse_args(argv)

    if args.healthcheck:
        print(json.dumps({"status": "healthy", "subsystem": "orders"}))
        return 0

    if args.workflow == "checkout":
        print(json.dumps({"workflow": "checkout", "steps_completed": 3, "status": "ok"}))
        return 0

    if args.workflow == "inventory":
        print(json.dumps({"workflow": "inventory", "items_checked": 5, "status": "ok"}))
        return 0

    print(json.dumps({"status": "ready"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


@dataclass
class SyntheticTargetApp:
    """In-memory and on-disk representation of a synthetic user application for testing."""

    root_dir: Path
    include_flaws: bool = True
    valid_auth_token: str = "test-owner-valid-token"
    endpoints: list[APIEndpointSpec] = field(default_factory=list)
    screens: list[DOMScreenSpec] = field(default_factory=list)
    system_flows: list[SystemFlowSpec] = field(default_factory=list)

    def dispatch_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, dict[str, str], str]:
        """Deterministic in-process HTTP request dispatcher for the synthetic target app."""
        req_headers = {k.lower(): v for k, v in (headers or {}).items()}
        parsed = urlsplit(path)
        route = parsed.path or "/"
        upper_method = method.upper()

        sec_headers = {
            "Content-Type": "application/json",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'",
            "Cache-Control": "no-store",
            "X-RateLimit-Remaining": "99",
        }

        if route == "/health" and upper_method == "GET":
            return 200, sec_headers, json.dumps({"status": "ok", "service": "synthetic-user-app"})

        if route == "/login" and upper_method == "GET":
            html = LOGIN_SCREEN_HTML_FLAWED if self.include_flaws else LOGIN_SCREEN_HTML_CLEAN
            html_headers = {**sec_headers, "Content-Type": "text/html; charset=utf-8"}
            return 200, html_headers, html

        if route == "/dashboard" and upper_method == "GET":
            html_headers = {**sec_headers, "Content-Type": "text/html; charset=utf-8"}
            return 200, html_headers, DASHBOARD_SCREEN_HTML

        if route == "/api/items" and upper_method == "GET":
            payload = {
                "items": [
                    {"id": "item-1", "name": "Industrial Sensor", "price": 25.0},
                    {"id": "item-2", "name": "Control Valve", "price": 80.0},
                ],
                "total": 2,
            }
            return 200, sec_headers, json.dumps(payload)

        if route == "/api/orders" and upper_method == "POST":
            auth_val = req_headers.get("authorization", "")
            expected_bearer = f"Bearer {self.valid_auth_token}"
            if auth_val != expected_bearer:
                return 401, sec_headers, json.dumps({"error": "unauthorized", "detail": "Valid bearer token required"})

            parsed_body: Any = body
            if isinstance(body, str):
                try:
                    parsed_body = json.loads(body)
                except json.JSONDecodeError:
                    return 400, sec_headers, json.dumps({"error": "invalid_json"})

            if not isinstance(parsed_body, dict):
                return 422, sec_headers, json.dumps({"error": "validation_error", "detail": "Object expected"})

            item_id = parsed_body.get("item_id")
            quantity = parsed_body.get("quantity")
            if not isinstance(item_id, str) or not item_id.strip():
                return 422, sec_headers, json.dumps({"error": "validation_error", "field": "item_id"})
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0 or quantity > 10000:
                return 422, sec_headers, json.dumps({"error": "validation_error", "field": "quantity"})

            return (
                201,
                sec_headers,
                json.dumps({"order_id": "ord-101", "item_id": item_id, "quantity": quantity, "status": "created"}),
            )

        if route == "/api/admin/debug":
            if self.include_flaws:
                # Intentional defensive findings when include_flaws=True:
                # 1. Missing authentication enforcement on an endpoint marked requires_auth=True
                # 2. Missing security headers (CSP, X-Content-Type-Options, X-Frame-Options)
                # 3. Sensitive token leaked in response body
                # 4. Unhandled 500 stack trace when malformed payload is sent via POST
                insecure_headers = {"Content-Type": "application/json"}
                if upper_method == "POST" and body == "__malformed__":
                    return (
                        500,
                        insecure_headers,
                        json.dumps(
                            {
                                "error": "Internal Server Error",
                                "traceback": "Traceback (most recent call last): File '/app/server.py', line 92",
                            }
                        ),
                    )
                return (
                    200,
                    insecure_headers,
                    json.dumps(
                        {
                            "debug": True,
                            "internal_token": "sk-syntheticdebug9876543210abcdef",
                            "status": "exposed",
                        }
                    ),
                )
            else:
                auth_val = req_headers.get("authorization", "")
                if auth_val != f"Bearer {self.valid_auth_token}":
                    return 401, sec_headers, json.dumps({"error": "unauthorized"})
                if upper_method == "POST" and not isinstance(body, dict):
                    return 400, sec_headers, json.dumps({"error": "bad_request"})
                return 200, sec_headers, json.dumps({"debug": False, "status": "locked"})

        return 404, sec_headers, json.dumps({"error": "not_found", "path": route})

    @contextlib.contextmanager
    def start_ephemeral_server(self) -> Iterator[str]:
        """Start a local ephemeral HTTP server bound to 127.0.0.1:0 and yield its base_url."""
        app_ref = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _handle_all(self, method: str) -> None:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else None
                parsed_body: Any = raw_body
                if raw_body:
                    try:
                        parsed_body = json.loads(raw_body)
                    except json.JSONDecodeError:
                        parsed_body = raw_body
                header_dict = {k: v for k, v in self.headers.items()}
                status, resp_headers, resp_text = app_ref.dispatch_request(
                    method=method,
                    path=self.path,
                    headers=header_dict,
                    body=parsed_body,
                )
                payload = resp_text.encode("utf-8")
                self.send_response(status)
                for hk, hv in resp_headers.items():
                    self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                self._handle_all("GET")

            def do_POST(self) -> None:
                self._handle_all("POST")

            def log_message(self, format: str, *args: Any) -> None:
                return

        class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        server = _ThreadedServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


def create_synthetic_target_app(root_dir: Path, *, include_flaws: bool = True) -> SyntheticTargetApp:
    """Materialize a synthetic user application on disk for offline multi-agent testing."""
    root_dir.mkdir(parents=True, exist_ok=True)
    app_dir = root_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    templates_dir = root_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = root_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    (app_dir / "__init__.py").write_text('"""Synthetic application package."""\n', encoding="utf-8")
    (app_dir / "contracts.py").write_text(
        CONTRACTS_PY_FLAWED if include_flaws else CONTRACTS_PY_CLEAN,
        encoding="utf-8",
    )
    (app_dir / "cli_process.py").write_text(CLI_PROCESS_PY, encoding="utf-8")

    login_html = LOGIN_SCREEN_HTML_FLAWED if include_flaws else LOGIN_SCREEN_HTML_CLEAN
    (templates_dir / "login.html").write_text(login_html, encoding="utf-8")
    (templates_dir / "dashboard.html").write_text(DASHBOARD_SCREEN_HTML, encoding="utf-8")

    if include_flaws:
        (logs_dir / "app.log").write_text(
            "2026-11-15T12:00:00Z INFO Starting synthetic service\n"
            "2026-11-15T12:00:05Z DEBUG Outbound client initialized with token=sk-syntheticlogsecret123456789\n",
            encoding="utf-8",
        )
        (root_dir / "requirements.txt").write_text("requests==2.19.0\npydantic>=2.7.0\n", encoding="utf-8")
    else:
        (logs_dir / "app.log").write_text(
            "2026-11-15T12:00:00Z INFO Starting synthetic service\n",
            encoding="utf-8",
        )
        (root_dir / "requirements.txt").write_text("pydantic>=2.7.0\n", encoding="utf-8")

    endpoints = [
        APIEndpointSpec(
            method="GET",
            path="/health",
            requires_auth=False,
            expected_status=200,
            expected_response_keys=["status", "service"],
        ),
        APIEndpointSpec(
            method="GET",
            path="/api/items",
            requires_auth=False,
            expected_status=200,
            expected_response_keys=["items", "total"],
            rate_limit_header="X-RateLimit-Remaining",
        ),
        APIEndpointSpec(
            method="POST",
            path="/api/orders",
            requires_auth=True,
            expected_status=201,
            request_schema={"item_id": "str", "quantity": "int"},
            valid_payload={"item_id": "item-1", "quantity": 2},
            expected_response_keys=["order_id", "status"],
        ),
        APIEndpointSpec(
            method="GET",
            path="/api/admin/debug",
            requires_auth=True,
            expected_status=200,
            expected_response_keys=["status"],
        ),
    ]

    screens = [
        DOMScreenSpec(
            name="login_screen",
            url_or_path=str(templates_dir / "login.html"),
            html_content=login_html,
            expected_selectors=[
                "[data-testid='login-email']",
                "[data-testid='login-password']",
                "[data-testid='login-submit']",
            ],
            expected_texts=["Welcome to Synthetic App", "Sign In"],
        ),
        DOMScreenSpec(
            name="orders_dashboard",
            url_or_path=str(templates_dir / "dashboard.html"),
            html_content=DASHBOARD_SCREEN_HTML,
            expected_selectors=["[data-testid='new-order-btn']", "[data-testid='items-link']"],
            expected_texts=["Orders Dashboard", "Create Order", "View Catalog"],
        ),
    ]

    system_flows = [
        SystemFlowSpec(
            name="cli_health_and_checkout_process",
            description="Run synthetic CLI process healthcheck and checkout workflow.",
            command=["-m", "app.cli_process", "--workflow", "checkout"],
            expected_exit_code=0,
            steps=[
                {"type": "http", "method": "GET", "path": "/health", "expected_status": 200},
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/orders",
                    "authenticated": True,
                    "payload": {"item_id": "item-1", "quantity": 3},
                    "expected_status": 201,
                },
                {"type": "http", "method": "GET", "path": "/api/items", "expected_status": 200},
            ],
        )
    ]

    return SyntheticTargetApp(
        root_dir=root_dir,
        include_flaws=include_flaws,
        endpoints=endpoints,
        screens=screens,
        system_flows=system_flows,
    )
