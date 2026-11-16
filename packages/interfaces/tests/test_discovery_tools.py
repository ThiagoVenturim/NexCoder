from __future__ import annotations

from nexcoder_interfaces.mcp.protocol import JSONRPCRequest
from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.tools import TOOL_DEFINITIONS
from nexcoder_interfaces.tools.discovery import (
    detectar_persona,
    gerar_perfil,
    iniciar_entrevista,
    responder,
)


def test_discovery_tools_registered_in_definitions():
    for tool_name in ["detectar_persona", "iniciar_entrevista", "responder", "gerar_perfil"]:
        assert tool_name in TOOL_DEFINITIONS
        assert TOOL_DEFINITIONS[tool_name].is_available is True
        assert TOOL_DEFINITIONS[tool_name].module == "discovery"


def test_detectar_persona_handler():
    res = detectar_persona(sinais={"has_repo": True, "has_running_product": True})
    assert res["status"] == "success"
    assert res["persona_code"] == "A"


def test_iniciar_responder_gerar_perfil_flow():
    # 1. Iniciar
    init_res = iniciar_entrevista(persona="B", project_name="Plataforma Beta")
    assert init_res["status"] == "success"
    sid = init_res["session_id"]
    assert init_res["persona_code"] == "B"

    # 2. Responder
    resp_res = responder(session_id=sid, resposta="Problema de comunicacao entre equipes")
    assert resp_res["status"] == "in_progress"
    assert "next_question" in resp_res

    # 3. Gerar perfil
    prof_res = gerar_perfil(session_id=sid)
    assert prof_res["persona"] == "idea_stage"
    assert prof_res["is_sanitized"] is True


def test_mcp_server_jsonrpc_calls():
    server = MCPServer()

    # Call detectar_persona via tools/call
    req = JSONRPCRequest(
        id=1,
        method="tools/call",
        params={
            "name": "detectar_persona",
            "arguments": {
                "sinais": {"is_idea_only": True, "has_repo": False},
            },
        },
    )
    res = server.handle_request(req)
    assert res is not None
    assert res.error is None
    assert res.result is not None
    assert "content" in res.result
    content_text = res.result["content"][0]["text"]
    assert '"persona_code": "B"' in content_text

    # Call iniciar_entrevista via tools/call
    req_init = JSONRPCRequest(
        id=2,
        method="tools/call",
        params={
            "name": "iniciar_entrevista",
            "arguments": {
                "persona": "A",
                "project_name": "MCP Legacy Test",
            },
        },
    )
    res_init = server.handle_request(req_init)
    assert res_init is not None
    assert res_init.error is None
    content_init = res_init.result["content"][0]["text"]
    assert '"persona_code": "A"' in content_init
    assert '"tech_stack"' in content_init
