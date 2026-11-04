from __future__ import annotations

import pytest
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
    assert KNOWN_MODULES["continuous-improvement"].available_in_develop is True


def test_module_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = get_module_statuses()
    assert len(statuses) >= 9

    # Installed modules in develop should be available
    assert statuses["ideation"]["available"] is True
    assert statuses["ideation"]["status"] == "available"
    assert statuses["capture"]["available"] is True
    assert statuses["capture"]["status"] == "available"
    assert statuses["serving"]["available"] is True
    assert statuses["serving"]["status"] == "available"
    assert statuses["continuous-improvement"]["available"] is True
    assert statuses["continuous-improvement"]["status"] == "available"

    # Modules not yet installed should be marked unavailable with clear message
    def _mock_installed(pkg: str) -> bool:
        return False if "nonexistent" in pkg else is_module_installed(pkg)

    monkeypatch.setattr("faccoder_interfaces.registry.is_module_installed", _mock_installed)
    monkeypatch.setitem(
        KNOWN_MODULES,
        "mock_mod",
        type(
            "ModuleInfoMock",
            (),
            {
                "name": "mock_mod",
                "package_name": "faccoder_nonexistent_mock",
                "description": "Mock module",
                "available_in_develop": False,
                "tools": [],
            },
        )(),
    )
    statuses_with_mock = get_module_statuses()
    assert statuses_with_mock["mock_mod"]["available"] is False
    assert statuses_with_mock["mock_mod"]["status"] == "unavailable"
    assert "not yet available in this release" in statuses_with_mock["mock_mod"]["message"]


def test_is_module_installed_nonexistent() -> None:
    assert is_module_installed("faccoder_nonexistent_xyz") is False
