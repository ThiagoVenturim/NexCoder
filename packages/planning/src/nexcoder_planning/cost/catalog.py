"""Reference pricing catalog loader, schema validator, and currency converter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nexcoder_planning.cost.models import (
    Currency,
    InfrastructureTarget,
    InfrastructureTier,
)

DEFAULT_CATALOG_PATH = Path(__file__).parent / "pricing_catalog.yaml"


class PricingCatalog:
    """Configurable pricing table loaded from YAML with currency conversion and source tracking."""

    def __init__(self, catalog_data: dict[str, Any] | None = None, catalog_path: Path | None = None) -> None:
        if catalog_data is not None:
            self.data = catalog_data
        else:
            path = catalog_path or DEFAULT_CATALOG_PATH
            if not path.is_file():
                raise FileNotFoundError(f"Pricing catalog YAML not found at {path}")
            with open(path, encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}

        meta = self.data.get("metadata", {})
        self.default_exchange_rate = float(meta.get("default_exchange_rate_usd_to_brl", 5.50))
        self.categories = self.data.get("categories", {})
        self._sources_registry: set[str] = set()

    def register_source(self, source: str) -> None:
        """Register a pricing source attribution."""
        if source:
            self._sources_registry.add(source)

    def get_registered_sources(self) -> list[str]:
        """Return all distinct sources collected during pricing lookups."""
        return sorted(self._sources_registry)

    def to_currency(
        self,
        amount_usd: float | None = None,
        amount_brl: float | None = None,
        target_currency: Currency = Currency.BRL,
        exchange_rate: float | None = None,
    ) -> float:
        """Convert an amount from USD or BRL into the requested target currency."""
        rate = exchange_rate if exchange_rate is not None and exchange_rate > 0 else self.default_exchange_rate

        if target_currency == Currency.BRL:
            if amount_brl is not None:
                return float(amount_brl)
            if amount_usd is not None:
                return float(amount_usd) * rate
            return 0.0
        elif target_currency == Currency.USD:
            if amount_usd is not None:
                return float(amount_usd)
            if amount_brl is not None:
                return float(amount_brl) / rate
            return 0.0
        return 0.0

    def get_infra_pricing(
        self,
        target: InfrastructureTarget,
        tier: InfrastructureTier,
        target_currency: Currency,
        exchange_rate: float,
    ) -> dict[str, Any]:
        """Lookup compute, database, and networking costs for the given target and tier."""
        targets = self.categories.get("infrastructure", {}).get("targets", {})
        target_name = target.value if hasattr(target, "value") else str(target)
        tier_name = tier.value if hasattr(tier, "value") else str(tier)

        target_cfg = targets.get(target_name, {})
        tier_cfg = target_cfg.get(tier_name, {})

        compute_usd = float(tier_cfg.get("compute_monthly_usd", 0.0))
        db_usd = float(tier_cfg.get("database_monthly_usd", 0.0))
        net_usd = float(tier_cfg.get("networking_monthly_usd", 0.0))
        source = str(tier_cfg.get("source", "Standard cloud pricing"))
        self.register_source(source)

        return {
            "compute_monthly": self.to_currency(
                amount_usd=compute_usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "database_monthly": self.to_currency(
                amount_usd=db_usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "networking_monthly": self.to_currency(
                amount_usd=net_usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "compute_usd": compute_usd,
            "database_usd": db_usd,
            "networking_usd": net_usd,
            "source": source,
        }

    def get_domain_pricing(self, domain_tld: str, target_currency: Currency, exchange_rate: float) -> dict[str, Any]:
        """Lookup initial registration and annual renewal costs for a domain TLD."""
        domains = self.categories.get("domains", {})
        key = domain_tld.replace(".", "").replace("-", "_")
        cfg = domains.get(key) or domains.get("com_br", {})

        init_brl = cfg.get("initial_cost_brl")
        init_usd = cfg.get("initial_cost_usd")
        ren_brl = cfg.get("annual_renewal_brl")
        ren_usd = cfg.get("annual_renewal_usd")
        source = str(cfg.get("source", "Domain registrar pricing"))
        self.register_source(source)

        initial = self.to_currency(
            amount_usd=init_usd, amount_brl=init_brl, target_currency=target_currency, exchange_rate=exchange_rate
        )
        renewal = self.to_currency(
            amount_usd=ren_usd, amount_brl=ren_brl, target_currency=target_currency, exchange_rate=exchange_rate
        )

        return {
            "initial_cost": initial,
            "annual_renewal": renewal,
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_trademark_pricing(
        self,
        jurisdiction: str,
        classes_count: int,
        include_legal: bool,
        target_currency: Currency,
        exchange_rate: float,
    ) -> dict[str, Any]:
        """Lookup official trademark fees and advisory rates for INPI, USPTO, or none."""
        tm_cat = self.categories.get("trademark", {})
        cfg = tm_cat.get(jurisdiction, tm_cat.get("inpi_br", {}))

        app_brl = cfg.get("application_fee_brl")
        app_usd = cfg.get("application_fee_usd")
        conc_brl = cfg.get("concession_first_decade_brl")
        conc_usd = cfg.get("concession_usd")
        legal_brl = cfg.get("legal_assistance_basic_brl") if include_legal else 0.0
        legal_usd = cfg.get("legal_assistance_basic_usd") if include_legal else 0.0
        source = str(cfg.get("source", "Official Patent & Trademark Office"))
        self.register_source(source)

        app_fee = self.to_currency(
            amount_usd=app_usd, amount_brl=app_brl, target_currency=target_currency, exchange_rate=exchange_rate
        ) * max(1, classes_count)
        conc_fee = self.to_currency(
            amount_usd=conc_usd, amount_brl=conc_brl, target_currency=target_currency, exchange_rate=exchange_rate
        ) * max(1, classes_count)
        legal_fee = self.to_currency(
            amount_usd=legal_usd, amount_brl=legal_brl, target_currency=target_currency, exchange_rate=exchange_rate
        )

        return {
            "application_fee": app_fee,
            "concession_fee": conc_fee,
            "legal_fee": legal_fee,
            "initial_cost": app_fee + legal_fee,
            "future_concession_cost": conc_fee,
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_email_pricing(self, provider: str, target_currency: Currency, exchange_rate: float) -> dict[str, Any]:
        """Lookup monthly email service cost."""
        email_cat = self.categories.get("email", {})
        cfg = email_cat.get(provider, email_cat.get("none", {}))
        usd = float(cfg.get("monthly_cost_usd", 0.0))
        source = str(cfg.get("source", "Email provider pricing"))
        self.register_source(source)

        return {
            "monthly_cost": self.to_currency(
                amount_usd=usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_cdn_pricing(self, cdn_key: str, target_currency: Currency, exchange_rate: float) -> dict[str, Any]:
        """Lookup monthly CDN and security service cost."""
        cdn_cat = self.categories.get("cdn_security", {})
        cfg = cdn_cat.get(cdn_key, cdn_cat.get("cloudflare_free", {}))
        usd = float(cfg.get("monthly_cost_usd", 0.0))
        source = str(cfg.get("source", "CDN/WAF pricing"))
        self.register_source(source)

        return {
            "monthly_cost": self.to_currency(
                amount_usd=usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_storage_pricing(self, storage_key: str, target_currency: Currency, exchange_rate: float) -> dict[str, Any]:
        """Lookup monthly object storage and backup cost."""
        storage_cat = self.categories.get("storage_backup", {})
        cfg = storage_cat.get(storage_key, storage_cat.get("s3_standard", {}))
        usd = float(cfg.get("monthly_cost_usd", 0.0))
        source = str(cfg.get("source", "Cloud storage pricing"))
        self.register_source(source)

        return {
            "monthly_cost": self.to_currency(
                amount_usd=usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_monitoring_pricing(
        self,
        monitoring_key: str,
        target_currency: Currency,
        exchange_rate: float,
    ) -> dict[str, Any]:
        """Lookup monthly monitoring, APM, and observability cost."""
        mon_cat = self.categories.get("monitoring", {})
        cfg = mon_cat.get(monitoring_key, mon_cat.get("free_tier", {}))
        usd = float(cfg.get("monthly_cost_usd", 0.0))
        source = str(cfg.get("source", "APM / Observability pricing"))
        self.register_source(source)

        return {
            "monthly_cost": self.to_currency(
                amount_usd=usd, target_currency=target_currency, exchange_rate=exchange_rate
            ),
            "source": source,
            "notes": cfg.get("notes", ""),
        }

    def get_labor_rate(self, role: str, target_currency: Currency, exchange_rate: float) -> float:
        """Lookup benchmark hourly rate for engineering roles."""
        labor_cat = self.categories.get("labor_rates", {})
        rates_brl = labor_cat.get("rates_brl_per_hour", {})
        rates_usd = labor_cat.get("rates_usd_per_hour", {})

        if target_currency == Currency.BRL:
            rate = rates_brl.get(role, rates_brl.get("average_developer", 160.00))
            source = str(rates_brl.get("source", "Tech market salary benchmark"))
        else:
            rate = rates_usd.get(role, rates_usd.get("average_developer", 55.00))
            source = str(rates_usd.get("source", "Tech market salary benchmark"))

        self.register_source(source)
        return float(rate)

    def get_ai_tier_pricing(self, tier: str) -> dict[str, float]:
        """Lookup per-million token pricing for AI model tiers."""
        tiers_cat = self.categories.get("ai_model_tiers", {})
        cfg = tiers_cat.get(tier, tiers_cat.get("medium", {}))
        inp = float(cfg.get("input_per_million_usd", 1.50))
        out = float(cfg.get("output_per_million_usd", 6.00))
        source = str(cfg.get("source", "Model provider token catalog"))
        self.register_source(source)

        return {
            "input_per_million_usd": inp,
            "output_per_million_usd": out,
        }
