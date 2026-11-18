from __future__ import annotations

from nexcoder_ideation.discovery.models import InterviewQuestion, PersonaType

QUESTIONS_PERSONA_A: list[InterviewQuestion] = [
    InterviewQuestion(
        id="tech_stack",
        persona=PersonaType.PERSONA_A,
        title="Stack tecnologica e arquitetura",
        prompt=(
            "Qual e a stack tecnologica atual da aplicacao? "
            "(Linguagens, frameworks, banco de dados, versao de runtime)"
        ),
        explanation="Permite ao NexCoder configurar analisadores sintaticos e preparar indexacao semantica de codigo.",
        category="architecture",
    ),
    InterviewQuestion(
        id="hosting_infra",
        persona=PersonaType.PERSONA_A,
        title="Hospedagem e infraestrutura",
        prompt=(
            "Onde a solucao roda hoje e como e feita a hospedagem/infraestrutura? "
            "(Nuvem AWS/Azure/GCP, bare-metal, containers Kubernetes/Docker, serverless)"
        ),
        explanation="Necessario para dimensionar calculo de custos operacionais e propor melhorias de IaC.",
        category="infrastructure",
    ),
    InterviewQuestion(
        id="pain_points",
        persona=PersonaType.PERSONA_A,
        title="Dores tecnicas e operacionais",
        prompt=(
            "Quais sao as maiores dores tecnicas hoje? (Codigo legado, divida tecnica, custo de nuvem sem controle, "
            "medo de quebrar em deploy, falta de testes ou observabilidade, dependencia de especialistas)"
        ),
        explanation="Orienta os agentes de qualidade, seguranca e refatoracao guiada para as areas mais criticas.",
        category="operations",
    ),
    InterviewQuestion(
        id="business_goals",
        persona=PersonaType.PERSONA_A,
        title="Metas e objetivos de negocio",
        prompt=(
            "Quais sao as principais metas de curto e medio prazo? (Reduzir custo de nuvem, destravar novas features "
            "sem quebrar legado, modernizar stack, escalar)"
        ),
        explanation="Alinha a priorizacao do backlog com o impacto comercial e reducao de risco.",
        category="strategy",
    ),
    InterviewQuestion(
        id="constraints_compliance",
        persona=PersonaType.PERSONA_A,
        title="Restricoes e conformidade",
        prompt=(
            "Existem restricoes tecnicas, orcamentarias ou requisitos regulatorios especificos? "
            "(LGPD, seguranca da informacao, janelas de manutencao, uptime exigido)"
        ),
        explanation="Configura os guardrails e politicas de conformidade dos agentes de seguranca.",
        category="compliance",
    ),
    InterviewQuestion(
        id="code_access",
        persona=PersonaType.PERSONA_A,
        title="Acesso ao repositorio e infraestrutura",
        prompt=(
            "Ha permissao e acesso ao repositorio ou infraestrutura para analise automatizada com gate de "
            "seguranca assinado?"
        ),
        explanation="Permite inspecao bottom-up, geracao de documentacao viva e auditoria estatica em alvo autorizado.",
        category="governance",
    ),
]

QUESTIONS_PERSONA_B: list[InterviewQuestion] = [
    InterviewQuestion(
        id="problem_statement",
        persona=PersonaType.PERSONA_B,
        title="Problema central e dor de mercado",
        prompt="Qual e o problema ou dor central que voce quer resolver, e como as pessoas resolvem isso hoje?",
        explanation="O squad de pesquisa e o juri usam isso para mapear concorrentes e validar se ha dor real.",
        category="problem",
    ),
    InterviewQuestion(
        id="target_audience",
        persona=PersonaType.PERSONA_B,
        title="Publico-alvo e cliente ideal",
        prompt=(
            "Quem e o publico-alvo ou usuario pretendido? (Segmento de mercado, perfil de usuario, tamanho de empresa)"
        ),
        explanation="Permite segmentar a pesquisa de mercado (TAM, SAM, SOM) e a disposicao a pagar.",
        category="market",
    ),
    InterviewQuestion(
        id="differentiation",
        persona=PersonaType.PERSONA_B,
        title="Proposta de valor e diferencial",
        prompt="Qual e o principal diferencial ou inovacao da sua solucao frente as alternativas existentes?",
        explanation="Alimenta a analise de posicionamento e matriz de defensibilidade da solucao.",
        category="value",
    ),
    InterviewQuestion(
        id="budget_investment",
        persona=PersonaType.PERSONA_B,
        title="Orcamento e investimento pretendido",
        prompt="Qual e a faixa de orcamento disponivel ou investimento planejado para construir e manter o MVP?",
        explanation="Permite a calculadora de custos dimensionar o escopo e a infraestrutura compativel.",
        category="financial",
    ),
    InterviewQuestion(
        id="timeline_mvp",
        persona=PersonaType.PERSONA_B,
        title="Prazo e cronograma desejado",
        prompt="Qual e o prazo ou horizonte esperado para colocar um MVP ou primeiro piloto para rodar?",
        explanation="O motor de planejamento usa o prazo para alocar sprints e definir escopo prioritario.",
        category="planning",
    ),
    InterviewQuestion(
        id="risks_assumptions",
        persona=PersonaType.PERSONA_B,
        title="Riscos e premissas a validar",
        prompt="Quais sao as principais duvidas, incertezas ou hipoteses que precisam ser comprovadas primeiro?",
        explanation="O juri avalia essas hipoteses para deliberar go, pivot ou no-go antes de gastar recursos.",
        category="risk",
    ),
]


def get_questions_for_persona(persona: PersonaType) -> list[InterviewQuestion]:
    """Retrieve the ordered list of interview questions for the given persona."""
    if persona == PersonaType.PERSONA_A:
        return list(QUESTIONS_PERSONA_A)
    return list(QUESTIONS_PERSONA_B)
