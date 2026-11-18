from __future__ import annotations

from nexcoder_ideation.discovery import (
    DiscoveryEngine,
    PersonaType,
    detectar_persona,
    gerar_perfil,
    sanitize_data,
    sanitize_text,
)


def test_sanitize_text_redacts_credentials():
    leaked = (
        "Aqui esta meu token ghp_123456789012345678901234567890123456 e chave sk-abcdefghijklmnopqrstuvwxyz123456. "
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcxfEmKGxDX "
        "Acesso com password: supersecretpassword123 e db postgres://admin:topsecretpw@localhost:5432/mydb"
    )
    sanitized = sanitize_text(leaked)
    assert "ghp_" not in sanitized
    assert "sk-" not in sanitized
    assert "Bearer" not in sanitized
    assert "supersecretpassword123" not in sanitized
    assert "topsecretpw" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized


def test_sanitize_data_nested_dict():
    raw = {
        "user": "developer",
        "api_key": "sk-123456789012345678901234",
        "nested": {
            "password": "secretpassword",
            "normal_note": "Apenas uma observacao comum",
        },
    }
    clean = sanitize_data(raw)
    assert clean["api_key"] == "[REDACTED_SECRET]"
    assert clean["nested"]["password"] == "[REDACTED_SECRET]"
    assert clean["nested"]["normal_note"] == "Apenas uma observacao comum"


def test_detectar_persona_explicit_flags():
    # Persona A
    sinais_a = {"has_repo": True, "has_running_product": True, "has_company": True}
    res_a = detectar_persona(sinais_a)
    assert res_a["persona"] == PersonaType.PERSONA_A.value
    assert res_a["persona_code"] == "A"
    assert res_a["confidence"] >= 0.7

    # Persona B
    sinais_b = {"is_idea_only": True, "has_repo": False, "has_running_product": False}
    res_b = detectar_persona(sinais_b)
    assert res_b["persona"] == PersonaType.PERSONA_B.value
    assert res_b["persona_code"] == "B"
    assert res_b["confidence"] >= 0.7


def test_detectar_persona_text_heuristics():
    # Text A: legacy system in production with cloud costs and tech debt
    text_a = "Temos um sistema legado em producao na AWS com alta divida tecnica e precisamos refatorar o monolito."
    res_a = detectar_persona(text_a)
    assert res_a["persona"] == PersonaType.PERSONA_A.value
    assert res_a["persona_code"] == "A"

    # Text B: early idea without code, seeking market validation
    text_b = "Tenho apenas uma ideia de marketplace e quero validar mercado do zero antes de criar o primeiro mvp."
    res_b = detectar_persona(text_b)
    assert res_b["persona"] == PersonaType.PERSONA_B.value
    assert res_b["persona_code"] == "B"


def test_interview_flow_persona_a():
    engine = DiscoveryEngine()

    # 1. Iniciar entrevista Persona A
    start = engine.iniciar_entrevista(persona=PersonaType.PERSONA_A, project_name="Sistema Legado Corp")
    assert start["status"] == "success"
    assert start["persona_code"] == "A"
    assert start["total_questions"] == 6
    assert start["current_question"]["id"] == "tech_stack"

    sid = start["session_id"]

    # 2. Responder questoes em sequencia
    r1 = engine.responder(sid, "Python 3.10, FastAPI, PostgreSQL, Redis")
    assert r1["status"] == "in_progress"
    assert r1["next_question"]["id"] == "hosting_infra"

    r2 = engine.responder(sid, "AWS ECS Fargate com RDS PostgreSQL")
    assert r2["status"] == "in_progress"
    assert r2["next_question"]["id"] == "pain_points"

    r3 = engine.responder(sid, "Falta de testes integrados, custos crescentes de nuvem e receio em deploy")
    assert r3["status"] == "in_progress"
    assert r3["next_question"]["id"] == "business_goals"

    r4 = engine.responder(sid, "Reduzir custos em 30% e viabilizar novos modulos sem regressao")
    assert r4["status"] == "in_progress"
    assert r4["next_question"]["id"] == "constraints_compliance"

    r5 = engine.responder(sid, "Conformidade estrita com LGPD e SLA de 99.9%")
    assert r5["status"] == "in_progress"
    assert r5["next_question"]["id"] == "code_access"

    r6 = engine.responder(sid, "Acesso concedido ao repositorio GitHub com revisao por PR")
    assert r6["status"] == "completed"

    # 3. Gerar perfil de cenario
    profile = engine.gerar_perfil(session_id=sid)
    assert profile["persona"] == PersonaType.PERSONA_A.value
    assert profile["project_name"] == "Sistema Legado Corp"
    assert profile["persona_a_details"] is not None
    assert profile["persona_b_details"] is None
    assert "code-intel/GraphRAG" in profile["recommended_pipeline"]
    assert "quality-agents" in profile["recommended_pipeline"]
    assert "security-audit-gate" in profile["recommended_pipeline"]
    assert profile["pipeline_readiness"]["ready_for_code_intel"] is True
    assert profile["pipeline_readiness"]["ready_for_security_gate"] is True
    assert profile["is_sanitized"] is True


def test_interview_flow_persona_b():
    engine = DiscoveryEngine()

    # 1. Iniciar entrevista Persona B
    start = engine.iniciar_entrevista(persona=PersonaType.PERSONA_B, project_name="App Inovador")
    assert start["status"] == "success"
    assert start["persona_code"] == "B"
    assert start["total_questions"] == 6
    assert start["current_question"]["id"] == "problem_statement"

    sid = start["session_id"]

    # 2. Responder questoes em sequencia
    r1 = engine.responder(sid, "Profissionais autonomos perdem 5 horas semanais organizando notas fiscais")
    assert r1["next_question"]["id"] == "target_audience"

    r2 = engine.responder(sid, "Prestadores de servico MEI no Brasil")
    assert r2["next_question"]["id"] == "differentiation"

    r3 = engine.responder(sid, "Captura automatica via WhatsApp e conciliacao tributaria instantanea")
    assert r3["next_question"]["id"] == "budget_investment"

    r4 = engine.responder(sid, "Ate R$ 15.000 para validacao do piloto")
    assert r4["next_question"]["id"] == "timeline_mvp"

    r5 = engine.responder(sid, "6 semanas para o primeiro prototipo funcional")
    assert r5["next_question"]["id"] == "risks_assumptions"

    r6 = engine.responder(sid, "Adesao dos usuarios a interface conversacional e APIs municipais")
    assert r6["status"] == "completed"

    # 3. Gerar perfil de cenario
    profile = engine.gerar_perfil(session_id=sid)
    assert profile["persona"] == PersonaType.PERSONA_B.value
    assert profile["project_name"] == "App Inovador"
    assert profile["persona_b_details"] is not None
    assert profile["persona_a_details"] is None
    assert "research-squad" in profile["recommended_pipeline"]
    assert "jury-committee" in profile["recommended_pipeline"]
    assert "prd-generator" in profile["recommended_pipeline"]
    assert profile["pipeline_readiness"]["ready_for_research"] is True
    assert profile["pipeline_readiness"]["ready_for_jury"] is True
    assert profile["is_sanitized"] is True


def test_discovery_sanitizes_answers_in_session():
    engine = DiscoveryEngine()
    start = engine.iniciar_entrevista(persona=PersonaType.PERSONA_A)
    sid = start["session_id"]

    # Injeta credencial acidental na resposta
    leaked_answer = (
        "Stack: Python, senha do banco password: secret123 com token ghp_111111111111111111111111111111111111"
    )
    engine.responder(sid, leaked_answer)
    profile = engine.gerar_perfil(session_id=sid)

    tech_stack_ans = profile["answers"].get("tech_stack", "")
    assert "secret123" not in tech_stack_ans
    assert "ghp_" not in tech_stack_ans
    assert "[REDACTED_SECRET]" in tech_stack_ans
    assert profile["is_sanitized"] is True


def test_gerar_perfil_direct_answers():
    # Test generation directly without interview session
    answers = {
        "problem_statement": "Validar demanda por plataforma de aluguel de equipamentos",
        "target_audience": "Pequenas locadoras de maquinas",
        "differentiation": "Gestao de contratos sem papel",
    }
    profile = gerar_perfil(answers=answers, persona="B", project_name="Locadora Tech")
    assert profile["persona"] == PersonaType.PERSONA_B.value
    assert profile["persona_b_details"]["problem_statement"].startswith("Validar demanda")
    assert len(profile["recommended_pipeline"]) > 0
    assert profile["is_sanitized"] is True
