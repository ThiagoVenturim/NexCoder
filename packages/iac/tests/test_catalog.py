"""Tests for reference architecture catalog and sizing tiers."""

import pytest
from nexcoder_iac.catalog import ArchitectureCatalog
from nexcoder_iac.models import ArchitectureTier, DatabaseEngine, IaCTarget
from nexcoder_iac.pricing import estimate_monthly_cost


def test_catalog_list_architectures():
    archs = ArchitectureCatalog.list_architectures()
    assert len(archs) >= 5
    ids = [a["id"] for a in archs]
    assert "simple_app" in ids
    assert "app_database" in ids
    assert "queue_worker" in ids
    assert "microservices" in ids
    assert "ai_serving" in ids


def test_catalog_simple_app_tiers():
    starter = ArchitectureCatalog.get("simple_app", tier=ArchitectureTier.STARTER)
    assert starter.tier == ArchitectureTier.STARTER
    assert len(starter.services) == 1
    assert starter.services[0].cpu_cores == 0.5
    assert not starter.load_balancer

    prod = ArchitectureCatalog.get("simple_app", tier=ArchitectureTier.PRODUCTION)
    assert prod.tier == ArchitectureTier.PRODUCTION
    assert prod.services[0].replicas == 2
    assert prod.load_balancer


def test_catalog_app_database():
    spec = ArchitectureCatalog.get("app_database", target=IaCTarget.AWS, tier=ArchitectureTier.STANDARD)
    assert spec.database is not None
    assert spec.database.engine == DatabaseEngine.POSTGRES
    assert spec.database.managed is True
    assert spec.database.storage_gb == 20

    cost = estimate_monthly_cost(spec)
    assert cost > 0.0


def test_catalog_queue_worker():
    spec = ArchitectureCatalog.get("queue_worker", target=IaCTarget.HETZNER, tier=ArchitectureTier.STANDARD)
    assert spec.cache is True
    assert spec.queue_worker is True
    assert len(spec.services) == 2
    names = [s.name for s in spec.services]
    assert any("api" in n for n in names)
    assert any("worker" in n for n in names)


def test_catalog_microservices():
    spec = ArchitectureCatalog.get("microservices", target=IaCTarget.DIGITALOCEAN, tier=ArchitectureTier.PRODUCTION)
    assert len(spec.services) == 3
    assert spec.database is not None
    assert spec.load_balancer is True
    cost = estimate_monthly_cost(spec)
    assert cost > 50.0


def test_catalog_ai_serving():
    spec = ArchitectureCatalog.get("ai_serving", target=IaCTarget.LOCAL_COMPOSE, profile="vllm")
    assert spec.ai_serving is not None
    assert spec.ai_serving.enabled is True
    assert spec.ai_serving.profile == "vllm"
    assert spec.ai_serving.port == 8000


def test_catalog_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown architecture 'non_existent'"):
        ArchitectureCatalog.get("non_existent")
