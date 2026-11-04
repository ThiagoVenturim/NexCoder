from __future__ import annotations

from faccoder_interfaces.registry import (
    KNOWN_MODULES,
    get_module_statuses,
    is_module_installed,
)


def test_known_modules_configuration() -> None:
    assert "ideation" in KNOWN_MODULES
    assert "planning" in KNOWN_MODULES
    assert "code" in KNOWN_MODULES
    assert "security" in KNOWN_MODULES
    assert "agents" in KNOWN_MODULES

    # Modules in develop
    assert "capture" in KNOWN_MODULES
    assert KNOWN_MODULES["capture"].available_in_develop is True
    assert "serving" in KNOWN_MODULES
    assert KNOWN_MODULES["serving"].available_in_develop is True
    assert "control" in KNOWN_MODULES
    assert KNOWN_MODULES["control"].available_in_develop is False
    assert "continuous-improvement" in KNOWN_MODULES
    assert KNOWN_MODULES["continuous-improvement"].available_in_develop is False


def test_module_statuses() -> None:
    statuses = get_module_statuses()
    assert len(statuses) >= 9

    # Installed modules in develop should be available
    assert statuses["ideation"]["available"] is True
    assert statuses["ideation"]["status"] == "available"
    assert statuses["capture"]["available"] is True
    assert statuses["capture"]["status"] == "available"
    assert statuses["serving"]["available"] is True
    assert statuses["serving"]["status"] == "available"

    # Modules not yet in develop should be marked unavailable with clear message
    assert statuses["continuous-improvement"]["available"] is False
    assert statuses["continuous-improvement"]["status"] == "unavailable"
    assert "not yet available in this release" in statuses["continuous-improvement"]["message"]


def test_is_module_installed_nonexistent() -> None:
    assert is_module_installed("faccoder_nonexistent_xyz") is False
