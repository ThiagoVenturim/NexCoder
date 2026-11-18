from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from nexcoder_ideation.discovery.models import (
    InterviewSession,
    InterviewState,
    PersonaADetails,
    PersonaBDetails,
    PersonaType,
    ScenarioProfile,
)
from nexcoder_ideation.discovery.questions import get_questions_for_persona
from nexcoder_ideation.discovery.sanitizer import sanitize_data, sanitize_text

logger = logging.getLogger(__name__)


def _normalize_persona(raw: str | PersonaType | None) -> PersonaType:
    if isinstance(raw, PersonaType):
        return raw
    val = str(raw or "").strip().lower()
    if val in ("a", "persona_a", "persona a", "established", "established_product", "empresa", "produto"):
        return PersonaType.PERSONA_A
    return PersonaType.PERSONA_B


class DiscoveryEngine:
    """Core engine responsible for persona detection, branching onboarding interviews, and scenario profiling."""

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}

    def detectar_persona(self, sinais: dict[str, Any] | str | None = None) -> dict[str, Any]:
        """Detect whether the user is Persona A (established product/company) or Persona B (idea stage / pain only)."""
        if sinais is None:
            sinais = {}

        raw_text = ""
        structured_signals: dict[str, Any] = {}
        if isinstance(sinais, str):
            raw_text = sinais.strip()
        elif isinstance(sinais, dict):
            structured_signals = dict(sinais)
            parts = [
                str(structured_signals.get("description", "")),
                str(structured_signals.get("context", "")),
                str(structured_signals.get("raw_text", "")),
                str(structured_signals.get("notes", "")),
            ]
            raw_text = " ".join(p for p in parts if p).strip()

        score_a = 0
        score_b = 0
        detected_signals: list[str] = []

        # 1. Explicit boolean / structured flags
        if structured_signals.get("has_repo") is True:
            score_a += 3
            detected_signals.append("has_repo=True")
        if structured_signals.get("has_running_product") is True:
            score_a += 3
            detected_signals.append("has_running_product=True")
        if structured_signals.get("has_company") is True:
            score_a += 2
            detected_signals.append("has_company=True")
        if structured_signals.get("has_team") is True:
            score_a += 2
            detected_signals.append("has_team=True")

        if structured_signals.get("is_idea_only") is True:
            score_b += 4
            detected_signals.append("is_idea_only=True")
        if structured_signals.get("has_repo") is False:
            score_b += 2
            detected_signals.append("has_repo=False")
        if structured_signals.get("has_running_product") is False:
            score_b += 2
            detected_signals.append("has_running_product=False")
        if structured_signals.get("has_team") is False:
            score_b += 1
            detected_signals.append("has_team=False")

        # 2. Text heuristics
        text_lower = raw_text.lower()

        keywords_a = [
            ("legado", 2),
            ("legacy", 2),
            ("em producao", 3),
            ("no ar", 2),
            ("repositorio", 2),
            ("repo", 1),
            ("divida tecnica", 2),
            ("refatorar", 2),
            ("nosso produto", 3),
            ("minha empresa", 2),
            ("clientes ativos", 3),
            ("nuvem", 1),
            ("aws", 1),
            ("azure", 1),
            ("banco de dados", 1),
            ("desenvolvedores", 2),
            ("deploy", 1),
            ("monolito", 2),
            ("microservicos", 2),
            ("custo de nuvem", 2),
        ]

        keywords_b = [
            ("so uma ideia", 4),
            ("apenas uma ideia", 4),
            ("apenas ideia", 4),
            ("so ideia", 4),
            ("tenho uma ideia", 3),
            ("quero criar", 2),
            ("do zero", 3),
            ("sem codigo", 3),
            ("sem produto", 3),
            ("sem repo", 3),
            ("validar ideia", 3),
            ("validar mercado", 3),
            ("saber se tem mercado", 3),
            ("ideia de produto", 2),
            ("primeiro mvp", 3),
            ("tirar do papel", 3),
            ("nao tenho time", 2),
            ("dor de mercado", 2),
        ]

        for kw, weight in keywords_a:
            if kw in text_lower:
                score_a += weight
                detected_signals.append(f"keyword_a:{kw}")

        for kw, weight in keywords_b:
            if kw in text_lower:
                score_b += weight
                detected_signals.append(f"keyword_b:{kw}")

        # Decide persona
        if score_a > score_b:
            persona = PersonaType.PERSONA_A
            persona_code = "A"
            persona_name = "Empresa estruturada com produto e codigo existente"
            rationale = "Sinais identificados apontam para produto ja ativo, repositorio ou codebase em producao."
            total = score_a + score_b
            confidence = round(min(0.99, max(0.65, score_a / (total if total > 0 else 1))), 2)
        else:
            persona = PersonaType.PERSONA_B
            persona_code = "B"
            persona_name = "Estagio de ideia inicial ou validacao de dor"
            rationale = (
                "Sinais indicam foco em concepcao, validacao de mercado ou construcao do zero sem codigo preexistente."
            )
            total = score_a + score_b
            confidence = round(min(0.99, max(0.65, score_b / (total if total > 0 else 1) if score_b > 0 else 0.8)), 2)

        return {
            "status": "success",
            "persona": persona.value,
            "persona_code": persona_code,
            "persona_name": persona_name,
            "confidence": confidence,
            "rationale": rationale,
            "detected_signals": detected_signals,
            "scores": {"score_a": score_a, "score_b": score_b},
        }

    def iniciar_entrevista(
        self,
        persona: str | PersonaType | None = None,
        sinais: dict[str, Any] | str | None = None,
        session_id: str | None = None,
        project_name: str = "Novo Projeto",
    ) -> dict[str, Any]:
        """Start a guided branching interview based on persona classification."""
        if not persona:
            detection = self.detectar_persona(sinais)
            persona_type = PersonaType(detection["persona"])
        else:
            persona_type = _normalize_persona(persona)

        questions = get_questions_for_persona(persona_type)
        sid = session_id or f"sess-{uuid.uuid4().hex[:8]}"

        session = InterviewSession(
            session_id=sid,
            persona=persona_type,
            state=InterviewState.IN_PROGRESS,
            questions=questions,
            current_index=0,
            answers={},
            metadata={"project_name": project_name},
            audit_log=[
                {
                    "event": "interview_started",
                    "persona": persona_type.value,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        )
        self._sessions[sid] = session

        current_q = questions[0]
        return {
            "status": "success",
            "session_id": sid,
            "persona": persona_type.value,
            "persona_code": "A" if persona_type == PersonaType.PERSONA_A else "B",
            "state": session.state.value,
            "total_questions": len(questions),
            "current_index": 0,
            "current_question": {
                "id": current_q.id,
                "title": current_q.title,
                "prompt": current_q.prompt,
                "explanation": current_q.explanation,
                "category": current_q.category,
            },
            "message": "Entrevista iniciada com sucesso. Responda a pergunta atual para prosseguir.",
        }

    def responder(
        self,
        session_id: str,
        resposta: str,
        question_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit an answer to the current interview question, advancing to the next or concluding."""
        session = self._sessions.get(session_id)
        if not session:
            return {
                "status": "error",
                "message": f"Sessao de entrevista '{session_id}' nao encontrada.",
            }

        if session.current_index >= len(session.questions):
            return {
                "status": "completed",
                "session_id": session_id,
                "message": "Todas as perguntas ja foram respondidas. Voce pode gerar o perfil com gerar_perfil.",
            }

        current_q = session.questions[session.current_index]
        target_qid = question_id or current_q.id

        # Sanitize answer immediately to prevent sensitive credential storage
        clean_answer = sanitize_text(str(resposta or "").strip())
        session.answers[target_qid] = clean_answer

        session.audit_log.append(
            {
                "event": "answer_recorded",
                "question_id": target_qid,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        session.current_index += 1

        if session.current_index < len(session.questions):
            next_q = session.questions[session.current_index]
            return {
                "status": "in_progress",
                "session_id": session_id,
                "answered_question_id": target_qid,
                "progress": f"{session.current_index}/{len(session.questions)}",
                "current_index": session.current_index,
                "next_question": {
                    "id": next_q.id,
                    "title": next_q.title,
                    "prompt": next_q.prompt,
                    "explanation": next_q.explanation,
                    "category": next_q.category,
                },
            }

        session.state = InterviewState.COMPLETED
        return {
            "status": "completed",
            "session_id": session_id,
            "answered_question_id": target_qid,
            "progress": f"{len(session.questions)}/{len(session.questions)}",
            "message": "Entrevista concluida com sucesso. Execute gerar_perfil para consolidar o perfil de cenario.",
            "total_answers": len(session.answers),
        }

    def gerar_perfil(
        self,
        session_id: str | None = None,
        answers: dict[str, str] | None = None,
        persona: str | PersonaType | None = None,
        project_name: str = "Novo Projeto",
        raw_signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate the final structured ScenarioProfile that feeds downstream pipeline stages."""
        session: InterviewSession | None = None
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]

        if session:
            final_persona = session.persona or PersonaType.PERSONA_B
            final_answers = dict(session.answers)
            if answers:
                final_answers.update(answers)
            p_name = session.metadata.get("project_name", project_name)
            sid = session.session_id
            audit_events = list(session.audit_log)
        else:
            final_persona = _normalize_persona(persona) if persona else PersonaType.PERSONA_B
            final_answers = dict(answers or {})
            p_name = project_name
            sid = session_id or f"sess-{uuid.uuid4().hex[:8]}"
            audit_events = []

        # Sanitize all answers and signals
        clean_answers = {k: sanitize_text(str(v)) for k, v in final_answers.items()}
        clean_signals = sanitize_data(raw_signals or {})

        persona_a_details: PersonaADetails | None = None
        persona_b_details: PersonaBDetails | None = None

        if final_persona == PersonaType.PERSONA_A:
            # Map Persona A responses
            stack_text = clean_answers.get("tech_stack", "")
            stack_list = [s.strip() for s in stack_text.replace(";", ",").split(",") if s.strip()]
            pain_text = clean_answers.get("pain_points", "")
            pain_list = [p.strip() for p in pain_text.replace(";", ",").split(",") if p.strip()]
            goals_text = clean_answers.get("business_goals", "")
            goals_list = [g.strip() for g in goals_text.replace(";", ",").split(",") if g.strip()]
            const_text = clean_answers.get("constraints_compliance", "")
            const_list = [c.strip() for c in const_text.replace(";", ",").split(",") if c.strip()]

            persona_a_details = PersonaADetails(
                tech_stack=stack_list or [stack_text] if stack_text else [],
                hosting_infra=clean_answers.get("hosting_infra", ""),
                pain_points=pain_list or [pain_text] if pain_text else [],
                business_goals=goals_list or [goals_text] if goals_text else [],
                constraints_compliance=const_list or [const_text] if const_text else [],
                code_access_status=clean_answers.get("code_access", ""),
                has_repo=True,
                has_running_product=True,
            )

            recommended_pipeline = [
                "code-intel/GraphRAG",
                "quality-agents",
                "security-audit-gate",
                "cost-calculator",
                "architecture-refactor",
                "ci-cd-observability",
            ]
            stack_desc = ", ".join(persona_a_details.tech_stack) or "N/A"
            infra_desc = persona_a_details.hosting_infra or "N/A"
            summary = (
                f"Cenario Produto Ativo ({p_name}): Stack identificada ({stack_desc}), "
                f"infra em '{infra_desc}' com foco em sanar dores tecnicas e modernizacao segura."
            )
        else:
            # Map Persona B responses
            risks_text = clean_answers.get("risks_assumptions", "")
            risks_list = [r.strip() for r in risks_text.replace(";", ",").split(",") if r.strip()]

            persona_b_details = PersonaBDetails(
                problem_statement=clean_answers.get("problem_statement", ""),
                target_audience=clean_answers.get("target_audience", ""),
                value_proposition_diff=clean_answers.get("differentiation", ""),
                budget_range=clean_answers.get("budget_investment", ""),
                timeline=clean_answers.get("timeline_mvp", ""),
                risks_assumptions=risks_list or [risks_text] if risks_text else [],
                validation_hypotheses=[
                    f"Validacao de valor: {clean_answers.get('differentiation', '')[:80]}",
                    f"Apetite do publico: {clean_answers.get('target_audience', '')[:80]}",
                ]
                if clean_answers.get("differentiation")
                else [],
            )

            recommended_pipeline = [
                "research-squad",
                "jury-committee",
                "prd-generator",
                "cost-calculator",
                "mvp-iac-scaffolding",
            ]
            audience_desc = persona_b_details.target_audience or "usuarios"
            summary = (
                f"Cenario Ideacao ({p_name}): Ideia inicial focada em resolver dor de '{audience_desc}'. "
                f"Esteira direcionada para pesquisa competitiva, deliberacao de juri e geracao de PRD/MVP."
            )

        audit_events.append(
            {
                "event": "profile_generated",
                "persona": final_persona.value,
                "timestamp": datetime.now(UTC).isoformat(),
                "keys_present": list(clean_answers.keys()),
            }
        )

        pipeline_readiness = {
            "ready_for_research": final_persona == PersonaType.PERSONA_B,
            "ready_for_code_intel": final_persona == PersonaType.PERSONA_A and bool(persona_a_details.tech_stack),
            "ready_for_jury": final_persona == PersonaType.PERSONA_B and bool(persona_b_details.problem_statement),
            "ready_for_security_gate": final_persona == PersonaType.PERSONA_A,
            "ready_for_cost_calc": True,
        }

        profile = ScenarioProfile(
            persona=final_persona,
            project_name=p_name,
            session_id=sid,
            summary=summary,
            answers=clean_answers,
            raw_signals=clean_signals,
            persona_a_details=persona_a_details,
            persona_b_details=persona_b_details,
            recommended_pipeline=recommended_pipeline,
            pipeline_readiness=pipeline_readiness,
            audit_trail=audit_events,
            is_sanitized=True,
        )

        return profile.model_dump()


# Module-level default engine singleton
_DEFAULT_ENGINE = DiscoveryEngine()


def detectar_persona(sinais: dict[str, Any] | str | None = None) -> dict[str, Any]:
    """Detect whether user belongs to Persona A or B."""
    return _DEFAULT_ENGINE.detectar_persona(sinais)


def iniciar_entrevista(
    persona: str | PersonaType | None = None,
    sinais: dict[str, Any] | str | None = None,
    session_id: str | None = None,
    project_name: str = "Novo Projeto",
) -> dict[str, Any]:
    """Start guided onboarding interview."""
    return _DEFAULT_ENGINE.iniciar_entrevista(
        persona=persona,
        sinais=sinais,
        session_id=session_id,
        project_name=project_name,
    )


def responder(
    session_id: str,
    resposta: str,
    question_id: str | None = None,
) -> dict[str, Any]:
    """Answer question and advance interview."""
    return _DEFAULT_ENGINE.responder(
        session_id=session_id,
        resposta=resposta,
        question_id=question_id,
    )


def gerar_perfil(
    session_id: str | None = None,
    answers: dict[str, str] | None = None,
    persona: str | PersonaType | None = None,
    project_name: str = "Novo Projeto",
    raw_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate structured scenario profile for the pipeline."""
    return _DEFAULT_ENGINE.gerar_perfil(
        session_id=session_id,
        answers=answers,
        persona=persona,
        project_name=project_name,
        raw_signals=raw_signals,
    )
