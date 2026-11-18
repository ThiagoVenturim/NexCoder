"""Offline unit tests for specialist test agents (Issue #71)."""

from __future__ import annotations

from pathlib import Path

from nexcoder_security.campaign.agents import (
    ApiTestAgent,
    DomTestAgent,
    ProcessTestAgent,
    SecurityTestAgent,
    SystemTestAgent,
    UnitTestAgent,
    build_test_agent,
)
from nexcoder_security.campaign.models import CampaignConfig, TestType


class TestCampaignAgents:
    def test_build_test_agent_factory(self) -> None:
        for t_type in TestType:
            agent = build_test_agent(t_type, agent_index=2)
            assert agent.test_type == t_type
            assert agent.agent_id == f"agent-{t_type.value}-2"

    def test_unit_test_agent_detects_bare_except(self, tmp_path: Path) -> None:
        code_file = tmp_path / "bad_handler.py"
        code_file.write_text(
            """def risky_operation():
    try:
        val = 1 / 0
    except:
        pass
""",
            encoding="utf-8",
        )
        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.UNIT])
        agent = UnitTestAgent()
        res = agent.execute(config, tmp_path)

        assert res.test_type == TestType.UNIT
        assert res.tests_failed >= 1
        assert any("Bare except" in f.title for f in res.findings)
        bare_finding = next(f for f in res.findings if "Bare except" in f.title)
        assert len(bare_finding.steps_to_reproduce) >= 2
        assert "except:" in (bare_finding.reproduction_snippet or "")

    def test_system_test_agent_detects_missing_python_and_env(self, tmp_path: Path) -> None:
        # Create pyproject without requires-python and an unshielded .env
        pyproj = tmp_path / "pyproject.toml"
        pyproj.write_text("[project]\nname = 'test-pkg'\nversion = '0.1.0'\n", encoding="utf-8")
        env_f = tmp_path / ".env"
        env_f.write_text("DB_PASSWORD=supersecret\n", encoding="utf-8")

        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.SYSTEM])
        agent = SystemTestAgent()
        res = agent.execute(config, tmp_path)

        assert res.tests_failed >= 2
        titles = [f.title for f in res.findings]
        assert any("requires-python" in t for t in titles)
        assert any(".env file" in t for t in titles)

    def test_process_test_agent_evaluates_workflow_triggers(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        wf_file = wf_dir / "orphaned.yml"
        wf_file.write_text("name: Orphaned\njobs:\n  build:\n    runs-on: ubuntu-latest\n", encoding="utf-8")

        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.PROCESS])
        agent = ProcessTestAgent()
        res = agent.execute(config, tmp_path)

        assert any("lacks triggering triggers" in f.title for f in res.findings)

    def test_dom_test_agent_detects_missing_csrf_and_opener(self, tmp_path: Path) -> None:
        html_file = tmp_path / "login.html"
        html_file.write_text(
            """<!DOCTYPE html>
<html>
<body>
  <form action="/login" method="POST">
    <input type="text" name="username">
    <button type="submit">Log In</button>
  </form>
  <a href="https://external.com" target="_blank">Docs</a>
</body>
</html>""",
            encoding="utf-8",
        )
        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.DOM])
        agent = DomTestAgent()
        res = agent.execute(config, tmp_path)

        assert res.tests_failed >= 2
        titles = [f.title for f in res.findings]
        assert any("CSRF" in t for t in titles)
        assert any("target='_blank'" in t for t in titles)

    def test_api_test_agent_detects_unbounded_limit(self, tmp_path: Path) -> None:
        api_file = tmp_path / "routes.py"
        api_file.write_text(
            """@router.post("/items")
def create_item(payload: dict):
    return payload

@router.get("/items")
def list_items(limit: int = 100):
    return []
""",
            encoding="utf-8",
        )
        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.API])
        agent = ApiTestAgent()
        res = agent.execute(config, tmp_path)

        assert res.tests_failed >= 1
        titles = [f.title for f in res.findings]
        assert any("Unbounded query limit" in t for t in titles)

    def test_security_test_agent_runs_offline(self, tmp_path: Path) -> None:
        target_f = tmp_path / "secrets.py"
        target_f.write_text("API_KEY = 'fc_apr_9876543210abcdef'\n", encoding="utf-8")
        config = CampaignConfig(target=str(tmp_path), test_types=[TestType.SECURITY], owned_target=True)
        agent = SecurityTestAgent()
        res = agent.execute(config, tmp_path)
        assert res.status == "success"
        assert res.tests_run >= 1
