# Auditoria do nexcoder v0.1.0: O que Falta e o que Melhorar

## Resumo
A versao v0.1.0 do nexcoder entrega uma arquitetura monorepo solida e modular com 11 pacotes Python integrados e cobertura de testes automatizados de 86% (488 testes hermeticos passando em 40 segundos).
Entretanto, ha discrepancias significativas entre a promessa documental e a entrega concreta de codigo, notadamente o catalogo de agentes que entrega 40 personas (prometia 100+) e a ausencia de parsers AST para COBOL, OutSystems e C# em code-intel, apesar de afirmados em READMEs.
O onboarding inicial continha instrucoes incompletas e snippets com bugs de API que quebravam imediatamente a experiencia de novos usuarios, alem da ausencia total da pasta de exemplos praticos (examples/).
Na frente de seguranca, os controles essenciais de fail-closed, hash de tokens de aprovacao e isolamento de caminhos foram respeitados, mas identificou-se o uso de dominios inventados no MockSearchProvider de ideation.
Para a v0.2.0, priorizam-se 5 acoes P1 focadas em um repositorio de exemplo ponta a ponta, alinhamento de promessas dos READMEs, eliminacao de dominios inventados, onboarding executavel e empacotamento para distribuicao.

---

## Rodando do Zero

A auditoria simulou o fluxo exato de um novo usuario a partir de um ambiente limpo (Python 3.13 em ambiente isolado virtual `.venv-audit`):

1. **Criacao do ambiente e instalacao de dependencias**:
   - `docs/getting-started.md` orientava originalmente instalar apenas 4 pacotes (`packages/core`, `packages/code-intel`, `packages/agents`, `packages/planning`), omitindo os outros 7 pacotes (`capture`, `continuous-improvement`, `control`, `ideation`, `interfaces`, `security`, `serving`).
   - O guia orientava executar `ruff check packages scripts` e `python -m pytest packages`, mas nao instruia a instalacao do `ruff` nem do `pytest` no ambiente virtual, gerando erro de comando nao encontrado (`No module named pytest`).
   - Os problemas nas instrucoes de instalacao foram corrigidos diretamente no guia durante esta auditoria.

2. **Execucao dos verificadores e suite de testes**:
   - `python scripts/check_no_emoji.py`: Executado em 1,57s com 0 ocorrencias de emojis em todo o repositorio.
   - `ruff check packages scripts`: Executado em 7,99s com 0 violacoes de lint ou estilo.
   - `python -m pytest packages`: Executado em 40,44s com 488 testes passando e 0 falhas (100% de sucesso offline).

3. **Execucao de snippets do guia de Getting Started**:
   - *Snippet 1 (Tiered Model Invocation)*: Falhava com `ProviderNotInstalledError: Provider 'anthropic' needs an optional dependency` porque a configuracao padrao operava no preset `hybrid` sem que as chaves de API pagas ou os pacotes opcionais estivessem configurados. Corrigido com a adicao de `config.preset = "offline"`.
   - *Snippet 2 (Code Indexing and Retrieval)*: Executou com sucesso, indexando classes e recuperando simbolos via HyDE e fusao RRF.
   - *Snippet 3 (Agent Execution with LangGraph Pipeline)*: Falhava com multiplos erros:
     - `AgentCatalog.from_directory("agents")` apontava para pasta inexistente na raiz (o caminho real e `packages/agents/agents`).
     - `architect.template` acessava atributo inexistente (o atributo no modelo Pydantic `AgentSpec` e `prompt`).
     - `PromptBlock(name=..., prompt_template=...)` lancava `TypeError` porque o bloco aceita `user_prompt_template` ou `system_prompt`.
     - `builder.build()` lancava `AttributeError` porque o metodo do `PipelineBuilder` e `.compile()`, e a ligacao de nos requer `.add_sequence()` ou `.add_edge()`.
     - Todos os pontos foram corrigidos e validados no guia.

4. **Execucao das ferramentas de linha de comando (CLIs)**:
   - Foram validadas as 6 CLIs disponiveis com `--help` e comandos de exemplo sob o preset `offline`:
     - `nexcoder`: Subcomandos funcionais; validado `nexcoder run bugfix --pipeline -t "Fix null check"` com sucesso.
     - `nexcoder-agents`: Validado `nexcoder-agents list-pipelines` (retornou os 6 templates prontos).
     - `nexcoder-ci`: Validado `nexcoder-ci --dry-run` (retornou busca de tarefas pendentes).
     - `nexcoder-control`: Validado `nexcoder-control status` (exibiu tabela de consumo, chaves e alertas).
     - `nexcoder-security`: Validado `nexcoder-security scan packages/security --offline` (executou heuristica SAST, bandit e gitleaks).
     - `nexcoder-serving`: Validado `nexcoder-serving --profile ollama --output test-compose.yml` (gerou compose valido).

---

## Promessa x Entrega

| Funcionalidade / Promessa | Arquivos de Documentacao | Status Atual | Detalhes e Evidencias |
|---|---|---|---|
| **Squad de Pesquisa e Juri** | `docs/ideation-and-jury.md`, `README.md` | Entregue e testado | `ResearchSquad` e 4 analistas especializados em `packages/ideation`. Juri com 6 membros, rubrica ponderada e deliberacao em `jury/committee.py`. Testes completos em `packages/ideation/tests/`. |
| **Geracao e Decomposicao de PRD** | `docs/agentic-planning.md`, `docs/ideation-and-jury.md` | Entregue e testado | Decomposicao de PRD em Epicos, Historias e Tarefas com criterios Given/When/Then em `packages/planning/src/nexcoder_planning/prd.py`. |
| **Sprints em Git e Adaptadores Kanban** | `docs/agentic-planning.md`, `README.md` | Entregue e testado | Calculo de capacidade, deteccao de desvios, marcadores idempotentes (`<!-- nexcoder-id: <uuid> -->`), adaptadores GitHub (GraphQL v2), GitLab e Azure DevOps em `packages/planning/src/nexcoder_planning/adapters/`. |
| **RAG Lexico e Vetorial Local** | `docs/rag-fundamentals.md`, `README.md` | Entregue e testado | Busca hibrida combinando SQLite FTS5 (BM25) e embeddings locais/hash com fusao RRF e MMR em `packages/core/src/nexcoder_core/retrieval/`. |
| **Advanced RAG e Context Compression** | `docs/advanced-rag.md` | Entregue e testado | Expansao de query com HyDE (`query_expansion.py`), compressao de contexto (`compression.py`) e diversificacao MMR em `nexcoder_core`. |
| **GraphRAG e Comunidades Louvain** | `docs/graphrag.md`, `README.md` | Entregue e testado | Grafo de codigo (`CodeGraph`) em NetworkX, deteccao de comunidades por modularidade Louvain (`communities.py`) e geracao de documentacao bottom-up (`docgen/bottom_up.py`). |
| **Reranking com Cross-Encoder** | `docs/reranking.md` | Entregue e testado | Pipeline em dois estagios implementado em `nexcoder_core.retrieval.rerank.CrossEncoderReranker` com fallback heuristico offline. |
| **Linguagens: Python, Go, Java, JS/TS, C, C++, Rust** | `docs/languages.md` | Entregue e testado | Parsers baseados em Tree-sitter em `packages/code-intel/src/nexcoder_code_intel/parsers/treesitter.py` cobrindo funcoes, classes, metodos e imports. |
| **Linguagem: Object Pascal / Delphi** | `docs/languages.md` | Entregue e testado | Parser customizado em `packages/code-intel/src/nexcoder_code_intel/parsers/delphi.py` com suporte a `interface`/`implementation` e amarramentos de componentes visuais em arquivos `.dfm`. |
| **Linguagem: C#** | `packages/agents/README.md` | Parcial | Existe persona em `packages/agents/agents/stacks/csharp.md`, mas nao existe suporte no parser Tree-sitter (`EXT_TO_LANG` nao mapeia `.cs`). |
| **Linguagem: COBOL** | `packages/code-intel/README.md` | So documentado / Falso check | `packages/code-intel/README.md` marca `- [x] COBOL`, mas nenhum parser existe no codigo. Ha apenas persona `cobol-specialist` em agents. |
| **Linguagem: OutSystems (.oml)** | `packages/code-intel/README.md` | So documentado / Falso check | `packages/code-intel/README.md` marca `- [x] OutSystems .oml`, mas nenhum parser existe no codigo. Ha apenas skill e persona em agents. |
| **Model Registry (Abertos e Pagos)** | `docs/models-open-vs-paid.md` | Entregue e testado | Abstracao em 3 tiers (`small`, `medium`, `large`) suportando Anthropic, OpenAI, Google, Azure, Bedrock, Ollama e vLLM em `nexcoder_core.llm.registry`. |
| **Observabilidade e Tracing Langfuse** | `docs/observability-langfuse.md` | Entregue e testado | Tracing resiliente com circuit breaker automatico (no-op seguro em falhas de rede) e calculo de custos em `packages/core/src/nexcoder_core/observability/`. |
| **Perfis de Serving (vLLM e Ollama)** | `docs/serving-vllm-vs-ollama.md` | Entregue e testado | Geracao de `docker-compose` parametrizado, avaliacao de RAG com LLM judge e gerador de dataset RAFT em `packages/serving`. |
| **Control Plane e Governanca** | `docs/control-plane.md` | Entregue e testado | Gestao de API keys com teto em USD, rate limits, ledger append-only de auditoria, aprovacao de maquinas CLI, tokens de aprovacao humana e painel web em `packages/control`. |
| **Captura Web, Desktop e QA** | `docs/architecture.md` | Entregue e testado | Captura DOM Playwright, sanitizacao HAR, seletores estaveis, automacao desktop pywinauto/OCR, geracao Page Object Model e testes visuais em `packages/capture`. |
| **Security Gate e Scanners** | `docs/architecture.md` | Entregue e testado | Orquestracao de Semgrep, Bandit, Gitleaks, OSV, Trivy, Pip-audit, Syft, geracao SBOM e avaliacao fail-closed em `packages/security`. |
| **Melhoria Continua** | `docs/architecture.md` | Entregue e testado | Scheduler cron, monitor Langfuse, watcher de concorrentes, bridge automatica de issues para GitHub em `packages/continuous-improvement`. |
| **Catalogo de 100+ Agentes/Skills/Pipelines** | `README.md` | Parcial | O README promete "100+ agents". Existem concretamente 40 arquivos de agentes, 9 skills e 6 templates de pipeline (total de 55 itens combinados). |

---

## Problemas Encontrados

### Inconsistencias de Documentacao e Promessas
1. **Contagem de personas exagerada no README**:
   - `README.md:36`: Cita "Persona catalog (100+ agents)".
   - Realidade: Existem exatamente 40 agentes em `packages/agents/agents/`, 9 skills em `packages/agents/skills/` e 6 pipelines prontos em `packages/agents/src/nexcoder_agents/engine/pipelines/templates.py`. O total combinado e 55, longe de 100+.
2. **Promessa falsa de parsers no README de code-intel**:
   - `packages/code-intel/README.md:14`: Marca `- [x] Specialized parsers: Delphi (units, implementations, DFM forms), COBOL, OutSystems .oml`.
   - Realidade: Nao existe nenhum parser de COBOL ou OutSystems em `packages/code-intel/src/nexcoder_code_intel/parsers/`.
3. **Status de pacotes desatualizado no README raiz**:
   - `README.md:17-23` e `README.pt-BR.md:17-23`: Pacotes como `nexcoder-ideation`, `nexcoder-security`, `nexcoder-capture` constam como "In progress" e `control`, `interfaces`, `serving`, `continuous-improvement` constam como "Planned", embora todos os 11 estejam implementados e integrados no branch `develop`.
4. **Referencia a ferramenta descontinuada**:
   - `docs/maestri-workspaces.md`: Apresentava arquitetura baseada em ferramenta legada de orquestracao. (Corrigido para texto neutro de orquestracao futura).

### Codigo Morto e Dependencias
1. **Dependencias opcionais declaradas sem uso de codigo**:
   - `packages/planning/pyproject.toml:20`: Declara `cli = ["typer>=0.12"]`, mas o pacote `nexcoder-planning` nao implementa modulo `cli.py` nem entry point no `[project.scripts]`.
   - `packages/ideation/pyproject.toml:21`: Declara `cli = ["typer>=0.12"]`, mas nao possui modulo `cli.py`.
   - `packages/security/pyproject.toml:19`: Declara `cli = ["typer>=0.12"]`, porem a CLI em `packages/security/src/nexcoder_security/cli.py:1` utiliza a biblioteca padrao `argparse`, tornando o `typer` uma dependencia desnecessaria.
2. **Pasta de exemplos ausente**:
   - O padrao do repositorio em `oss-repo-standards` e as boas praticas open-source exigem pasta `examples/`. O diretorio nao existe no repositorio raiz.

### Seguranca e URLs Inventadas
1. **Dominios inventados em MockSearchProvider**:
   - `packages/ideation/src/nexcoder_ideation/search/providers.py:37-41`: Utiliza dominios ficticios como `reports.analyst-insights.org`, `benchmarks.open-market.org`, `feedback.community-pulse.net`, `specs.engineering-review.dev` e `compliance.standards-bulletin.org`. Viola a regra do portfolio de nao inventar URLs e o padrao RFC 2606 (deveriam ser `example.org` ou `example.com`).
2. **Cobertura de testes abaixo de 60% em modulos criticos**:
   - `packages/continuous-improvement/src/nexcoder_continuous_improvement/cli.py` (0%)
   - `packages/control/src/nexcoder_control/cli.py` (0%)
   - `packages/serving/src/nexcoder_serving/cli.py` (0%)
   - `packages/core/src/nexcoder_core/llm/registry.py` (35%)
   - `packages/core/src/nexcoder_core/observability/langfuse_safe.py` (35%)
   - `packages/core/src/nexcoder_core/retrieval/rerank.py` (36%)
   - `packages/core/src/nexcoder_core/retrieval/embeddings.py` (39%)
   - `packages/ideation/src/nexcoder_ideation/search/providers.py` (39%)
   - `packages/ideation/src/nexcoder_ideation/output/architecture.py` (42%)
   - `packages/planning/src/nexcoder_planning/adapters/azure_devops.py` (55%)
   - `packages/planning/src/nexcoder_planning/models.py` (55%)
   - `packages/security/src/nexcoder_security/scanners/osv.py` (57%)
   - `packages/ideation/src/nexcoder_ideation/research/specialists.py` (58%)

---

## Melhorias Priorizadas

| Prioridade | Esforco | Descricao da Melhoria | Justificativa |
|---|---|---|---|
| **P1** | M | **Criar pasta `examples/` com tutorial ponta a ponta reproduzivel**: Exemplo completo de intake de ideia, revisao de juri, geracao de PRD, indexacao AST de um mini-projeto Python e disparo de pipeline de testes em modo offline. | Sem um exemplo executavel completo, novos usuarios e adotantes nao conseguem ver a esteira operar de ponta a ponta sem ler o codigo fonte. |
| **P1** | P | **Corrigir dominios inventados em `MockSearchProvider`**: Substituir os dominios sinteticos de `packages/ideation/src/nexcoder_ideation/search/providers.py` por URIs reservadas RFC 2606 (`example.com`, `example.org`). | Conformidade rigorosa com a regra inegociavel do portfolio contra inventar contas e URLs. |
| **P1** | P | **Sincronizar README raiz e de pacotes com a realidade da entrega**: Atualizar status dos pacotes para "Available", ajustar o catalogo para 40 agentes e desmarcar COBOL/OutSystems no README de code-intel ate que os parsers existam. | Transparencia tecnica essencial para credibilidade de projeto open-source perante a comunidade e avaliadores. |
| **P1** | P | **Limpar dependencias declaradas sem uso**: Remover `cli = ["typer"]` de `packages/planning/pyproject.toml`, `packages/ideation/pyproject.toml` e `packages/security/pyproject.toml`. | Evita instalacao de dependencias fantasmas em ambientes de producao. |
| **P1** | M | **Testes unitarios para as CLIs nao testadas**: Criar suites de teste para `nexcoder_control/cli.py`, `nexcoder_ci/cli.py` e `nexcoder_serving/cli.py` elevando a cobertura de 0% para mais de 80%. | Garante que alteracoes de parametros e atualizacoes de bibliotecas de CLI nao quebrem os binarios publicos. |
| **P2** | M | **Onboarding em 5 minutos (`quickstart.py`)**: Script interativo ou comando `nexcoder demo` que inicializa um workspace temporario, roda o preset offline e apresenta o resultado em terminal formatado. | Reduz drasticamente a barreira de adocao e permite demonstracoes rapidas para partes interessadas. |
| **P2** | G | **Integracao nativa com NexHub como backend de execucao**: Adicionar camada de orquestracao onde pipelines do nexcoder operem como workers orientados a eventos para o NexHub. | Posiciona o nexcoder como o motor de inteligencia do ecossistema de ferramentas do Thiago. |
| **P2** | M | **Benchmarks numericos de RAG e Retrieval**: Criar benchmark reprodutivel em `benchmarks/` medindo latencia, memoria e precisao (Hit@K, MRR) do SQLite FTS5 vs sqlite-vec vs fusao RRF. | Prova quantitativa da superioridade da abordagem hibrida do nexcoder. |
| **P2** | M | **Site de documentacao estruturado com MkDocs Material**: Configurar `mkdocs.yml` com navegacao organizada por guias, referencia de API gerada por `mkdocstrings` e diagramas Mermaid integrados. | Melhora a navegabilidade de mais de 20 documentos densos que hoje estao apenas em Markdown puro no GitHub. |
| **P2** | P | **Melhoria nas mensagens de erro e orientacao de instalacao**: Ajustar o tratamento de `ProviderNotInstalledError` e dependencias ausentes em tempo de execucao para sugerir o comando exato de instalacao do pacote monorepo. | Impede que o usuario se sinta perdido ao tentar usar provedores online sem dependencias instaladas. |
| **P3** | M | **Pipeline de publicacao de pacotes no PyPI (preparacao)**: Estruturar workflow de release no GitHub Actions com validacao de build wheel e suporte a Trusted Publishing para o PyPI (nexcoder-core, nexcoder-code-intel, etc.). | Facilita a utilizacao de pacotes individuais (como `nexcoder-core` no `askdash` ou `Support Engine`) via `pip install`. |
| **P3** | P | **Demo gravada em formato GIF / SVG (Terminalizer ou VHS)**: Gravar fluxo de terminal demonstrando a deliberacao do juri e a indexacao de simbolos para inclusao no README. | Aumenta engajamento visual na pagina principal do repositorio no GitHub. |
| **P3** | G | **Parsers reais para COBOL e OutSystems**: Implementar gramaticas basicas Tree-sitter para C# e parsers dedicados para analise estatica de copybooks COBOL e metadados XML de pacotes OutSystems. | Atende plenamente a promessa de modernizacao de legado corporativo que diferencia o nexcoder de outros frameworks. |

---

## Proximos Passos Sugeridos

1. **Abertura e revisao de PR pelo Conductor**:
   - Submeter o branch `chore/audit-v0.1.0` contendo este relatorio e as correcoes criticas do guia de onboarding para revisao do Conductor.
2. **Priorizacao do lote P1 na proxima sprint**:
   - Abrir issues dedicadas para criacao da pasta `examples/` com mini-app ponta a ponta, alinhamento das contagens nos READMEs e substituicao dos dominios no MockSearchProvider.
3. **Evolucao para v0.1.1 / v0.2.0**:
   - Integrar benchmarks de RAG e estruturar o site MkDocs para preparacao do lancamento publico amplo.
