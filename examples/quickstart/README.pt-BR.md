# Quickstart nexcoder: Esteira de Entrega Ponta a Ponta Offline

Este exemplo demonstra como o nexcoder orquestra o ciclo completo de engenharia de software sem exigir chaves de API externas nem conexao com a internet.

## O Que Este Exemplo Mostra

O script executa uma esteira completa sobre o mini-projeto Python incluso (`sample_project/`):

1. **Intake de Ideia e Juri Arquitetural (`nexcoder-ideation`)**:
   Processa uma proposta ("add due dates to tasks") e avalia viabilidade de mercado, arquitetura e alinhamento atraves de seis personas automatizadas de jurados, devolvendo um veredito em consenso (GO / PIVOT / NO-GO).
2. **Geracao do PRD (`prd.md`)**:
   Sintetiza a analise inicial, citacoes de pesquisa competitiva, especificacao de arquitetura e rubrica do juri em um documento formal de requisitos.
3. **Planejamento de Sprints e Backlog (`nexcoder-planning`)**:
   Decompoe o PRD em Epicos, Historias de Usuario e Tarefas com criterios de aceite, calcula a capacidade da equipe (horas, velocidade, limites) e commita o backlog inicial em um repositorio Git local.
4. **Inteligencia de Codigo e GraphRAG (`nexcoder-code-intel`)**:
   Indexa os modulos de `sample_project/`, extrai simbolos AST para SQLite FTS5/vetorial e responde a uma consulta de busca semantica sobre o codigo existente.
5. **Esteira de Agentes Especializados (`nexcoder-agents`)**:
   Executa o fluxo de trabalho `bugfix-delivery` do catalogo de agentes com um modelo deterministico, identificando uma falha sutil no projeto de exemplo e sintetizando um patch validado.
6. **Gate de Seguranca (`nexcoder-security`)**:
   Analisa o codigo-fonte com scanners SAST offline (regras de Semgrep e Bandit) e valida politicas de liberacao contra niveis de severidade.

## Como Executar

Certifique-se de que o ambiente virtual esteja ativo e os pacotes do monorepo instalados em modo editavel:

```bash
# Executa o quickstart completo
python examples/quickstart/run_quickstart.py
```

Para gravar os artefatos em outro diretorio em vez de `.quickstart_artifacts`:

```bash
python examples/quickstart/run_quickstart.py --output-dir /caminho/para/artefatos
```

## O Que Esperar na Saida

O terminal exibe o progresso de cada etapa com indicadores claros:

```text
======================================================================
nexcoder Offline Quickstart: End-to-End Delivery Pipeline
======================================================================

[1/6] Ideation & Architectural Jury
----------------------------------------------------------------------
Idea Title:    Add due dates and deadline tracking to task management library
Jury Decision: GO (Consensus: True)
Votes:         5 GO / 1 PIVOT / 0 NO-GO (Total jurors: 6)

[2/6] PRD Generation
----------------------------------------------------------------------
PRD generated successfully from vetted architecture and jury rubric.
Total lines:   163

[3/6] Planning & Sprint Decomposition (Git Repository)
----------------------------------------------------------------------
Scheduled Sprint: Sprint-1
Planned Hours:    7.0h
Scheduled Tasks:  2
Git Repository:   .../planning_repo

[4/6] Code Intelligence Indexing & AST Code Search
----------------------------------------------------------------------
Source Files:     5 files indexed from sample_project
RAG Question:     How is overdue status evaluated in sample_project?
Retrieved Chunks: 2

[5/6] Multi-Agent Delivery Pipeline
----------------------------------------------------------------------
Pipeline:         bugfix-delivery
Execution Status: completed (dry_run mode)
Execution Steps:  5

[6/6] Security Release Gate Evaluation
----------------------------------------------------------------------
Target Scanned:   sample_project
Findings Count:   8
Gate Verdict:     PASSED
Summary:          Release APPROVED by security gate 'default-production-gate'.
```

Ao final, todos os artefatos ficam disponiveis na pasta de destino:
- `jury_verdict.json`: Votos do juri, pontuacao por criterio e pareceres divergentes.
- `prd.md`: Documento de requisitos completo em Markdown.
- `planning_repo/`: Repositorio Git com `BACKLOG.md` e `sprint_1.json`.
- `code_intel.db`: Banco SQLite com simbolos de codigo e busca textual.
- `rag_summary.txt`: Trechos de codigo recuperados e analise.
- `pipeline_run.json`: Trilha de execucao dos agentes e historico de passos.
- `security_gate_verdict.json`: Achados de analise estatica e parecer do gate.

## Como Trocar o Modo Offline por Modelos Reais

Por padrao, o script usa `MockSearchProvider` e `FakeChatModel` para rodar de forma autonoma em poucos segundos.

Para conectar provedores reais (Anthropic, OpenAI, Gemini ou modelos locais via Ollama/vLLM):

1. **Defina as Variaveis de Ambiente**:
   ```bash
   # Para Anthropic Claude
   export ANTHROPIC_API_KEY="sk-ant-..."

   # Para OpenAI
   export OPENAI_API_KEY="sk-..."

   # Para Google Gemini
   export GEMINI_API_KEY="..."

   # Para Ollama local
   export OLLAMA_BASE_URL="http://localhost:11434"
   ```

2. **Use `get_chat_model`**:
   Substitua `FakeChatModel(...)` por `get_chat_model`:
   ```python
   from nexcoder_core.llm.registry import get_chat_model

   # Tiers: 'small' (triagem rapida), 'medium' (codigo geral), 'large' (raciocinio complexo)
   model = get_chat_model("medium")
   ```

3. **Habilite Busca Web Real na Ideacao**:
   Em `IdeationPipeline`, use `allow_network=True` para consultar o DuckDuckGo ou outro mecanismo configurado:
   ```python
   from nexcoder_ideation.pipeline import IdeationPipeline

   pipeline = IdeationPipeline(allow_network=True, model=model)
   ```
