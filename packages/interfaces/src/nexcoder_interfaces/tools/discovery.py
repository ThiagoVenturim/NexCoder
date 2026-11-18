from __future__ import annotations

from typing import Any


def detectar_persona(sinais: dict[str, Any] | str | None = None) -> dict[str, Any]:
    """Detect whether user belongs to Persona A (established company/product) or Persona B (idea stage)."""
    try:
        from nexcoder_ideation.discovery import detectar_persona as _detectar
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    return _detectar(sinais=sinais)


def iniciar_entrevista(
    persona: str | None = None,
    sinais: dict[str, Any] | str | None = None,
    session_id: str | None = None,
    project_name: str = "Novo Projeto",
) -> dict[str, Any]:
    """Start a branching onboarding interview for Persona A or B."""
    try:
        from nexcoder_ideation.discovery import iniciar_entrevista as _iniciar
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    return _iniciar(
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
    """Submit an answer to the current interview question and receive the next question or completion."""
    try:
        from nexcoder_ideation.discovery import responder as _responder
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    return _responder(
        session_id=session_id,
        resposta=resposta,
        question_id=question_id,
    )


def gerar_perfil(
    session_id: str | None = None,
    answers: dict[str, str] | None = None,
    persona: str | None = None,
    project_name: str = "Novo Projeto",
    raw_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the structured scenario profile that feeds the NexCoder engineering pipeline."""
    try:
        from nexcoder_ideation.discovery import gerar_perfil as _gerar
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    return _gerar(
        session_id=session_id,
        answers=answers,
        persona=persona,
        project_name=project_name,
        raw_signals=raw_signals,
    )
