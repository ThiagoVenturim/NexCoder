"""Configuration loader for nexcoder email connectors and governance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EmailProviderType = Literal["gmail", "outlook", "smtp", "none", "auto"]


class GmailOAuthSettings(BaseModel):
    """OAuth2 configuration for Google Gmail API."""

    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    user_email: str | None = None

    def is_configured(self) -> bool:
        """Check if minimum required credentials for Gmail are present."""
        has_direct_token = bool(self.access_token)
        has_refresh_flow = bool(self.client_id and self.client_secret and self.refresh_token)
        return has_direct_token or has_refresh_flow


class OutlookGraphSettings(BaseModel):
    """OAuth2 configuration for Microsoft Graph API / Outlook."""

    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    tenant_id: str = "common"
    user_email: str | None = None

    def is_configured(self) -> bool:
        """Check if minimum required credentials for Microsoft Graph are present."""
        has_direct_token = bool(self.access_token)
        has_refresh_flow = bool(self.client_id and self.client_secret and self.refresh_token)
        return has_direct_token or has_refresh_flow


class SMTPSettings(BaseModel):
    """Fallback generic SMTP configuration."""

    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str | None = None

    def is_configured(self) -> bool:
        """Check if SMTP host is configured."""
        return bool(self.host and self.host.strip())


class EmailSettings(BaseModel):
    """Central configuration for nexcoder email sending and policies."""

    default_provider: EmailProviderType = "auto"
    require_human_approval: bool = True
    max_recipients_per_send: int = 10
    rate_limits_rpm: dict[str, int] = Field(
        default_factory=lambda: {
            "gmail": 60,
            "outlook": 30,
            "smtp": 30,
        }
    )
    gmail: GmailOAuthSettings = Field(default_factory=GmailOAuthSettings)
    outlook: OutlookGraphSettings = Field(default_factory=OutlookGraphSettings)
    smtp: SMTPSettings = Field(default_factory=SMTPSettings)

    @classmethod
    def from_env(cls, env_file: Path | str | None = None) -> EmailSettings:
        """Load settings from environment variables with optional .env parsing."""
        env_dict = dict(os.environ)
        if env_file:
            path = Path(env_file).resolve()
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith("#") and "=" in clean:
                        k, v = clean.split("=", 1)
                        env_dict.setdefault(k.strip(), v.strip().strip("'\""))

        provider_raw = env_dict.get("NEXCODER_EMAIL_PROVIDER", "auto").lower()
        if provider_raw not in ("gmail", "outlook", "smtp", "none", "auto"):
            provider_raw = "auto"

        require_appr_str = env_dict.get("NEXCODER_EMAIL_REQUIRE_APPROVAL", "true").lower()
        require_approval = require_appr_str not in ("0", "false", "no", "off")

        try:
            max_recip = int(env_dict.get("NEXCODER_EMAIL_MAX_RECIPIENTS", "10"))
        except ValueError:
            max_recip = 10

        gmail_settings = GmailOAuthSettings(
            client_id=env_dict.get("NEXCODER_GMAIL_CLIENT_ID"),
            client_secret=env_dict.get("NEXCODER_GMAIL_CLIENT_SECRET"),
            refresh_token=env_dict.get("NEXCODER_GMAIL_REFRESH_TOKEN"),
            access_token=env_dict.get("NEXCODER_GMAIL_ACCESS_TOKEN"),
            user_email=env_dict.get("NEXCODER_GMAIL_USER_EMAIL"),
        )

        outlook_settings = OutlookGraphSettings(
            client_id=env_dict.get("NEXCODER_OUTLOOK_CLIENT_ID"),
            client_secret=env_dict.get("NEXCODER_OUTLOOK_CLIENT_SECRET"),
            refresh_token=env_dict.get("NEXCODER_OUTLOOK_REFRESH_TOKEN"),
            access_token=env_dict.get("NEXCODER_OUTLOOK_ACCESS_TOKEN"),
            tenant_id=env_dict.get("NEXCODER_OUTLOOK_TENANT_ID", "common"),
            user_email=env_dict.get("NEXCODER_OUTLOOK_USER_EMAIL"),
        )

        try:
            smtp_port = int(env_dict.get("NEXCODER_SMTP_PORT", "587"))
        except ValueError:
            smtp_port = 587

        smtp_tls = env_dict.get("NEXCODER_SMTP_USE_TLS", "true").lower() not in ("0", "false", "no")
        smtp_ssl = env_dict.get("NEXCODER_SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")

        smtp_settings = SMTPSettings(
            host=env_dict.get("NEXCODER_SMTP_HOST"),
            port=smtp_port,
            username=env_dict.get("NEXCODER_SMTP_USERNAME") or env_dict.get("NEXCODER_SMTP_USER"),
            password=env_dict.get("NEXCODER_SMTP_PASSWORD"),
            use_tls=smtp_tls,
            use_ssl=smtp_ssl,
            from_email=env_dict.get("NEXCODER_SMTP_FROM_EMAIL"),
        )

        gmail_rpm = int(env_dict.get("NEXCODER_EMAIL_RATE_LIMIT_GMAIL_RPM", "60"))
        outlook_rpm = int(env_dict.get("NEXCODER_EMAIL_RATE_LIMIT_OUTLOOK_RPM", "30"))
        smtp_rpm = int(env_dict.get("NEXCODER_EMAIL_RATE_LIMIT_SMTP_RPM", "30"))

        return cls(
            default_provider=provider_raw,  # type: ignore[arg-type]
            require_human_approval=require_approval,
            max_recipients_per_send=max_recip,
            rate_limits_rpm={
                "gmail": gmail_rpm,
                "outlook": outlook_rpm,
                "smtp": smtp_rpm,
            },
            gmail=gmail_settings,
            outlook=outlook_settings,
            smtp=smtp_settings,
        )

    def is_provider_configured(self, provider: str) -> bool:
        """Check if specified provider has required credentials."""
        clean = provider.lower()
        if clean == "gmail":
            return self.gmail.is_configured()
        if clean in ("outlook", "graph", "m365"):
            return self.outlook.is_configured()
        if clean == "smtp":
            return self.smtp.is_configured()
        return False

    def is_configured(self) -> bool:
        """Check if at least one sending provider is operational."""
        return (
            self.gmail.is_configured()
            or self.outlook.is_configured()
            or self.smtp.is_configured()
        )

    def get_preferred_provider(self) -> str:
        """Determine best configured provider based on preference and readiness."""
        if self.default_provider != "auto" and self.default_provider != "none":
            return self.default_provider

        # Auto detection: prefer Gmail, then Outlook, then SMTP
        if self.gmail.is_configured():
            return "gmail"
        if self.outlook.is_configured():
            return "outlook"
        if self.smtp.is_configured():
            return "smtp"
        return "none"
