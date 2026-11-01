# faccoder

Uma plataforma modular de codigo aberto para automacao do desenvolvimento de software, da concepcao a producao.

O `faccoder` orquestra o ciclo completo de entrega de software: intake de ideias e pesquisa de mercado, avaliacao arquitetural por comite julgador, geracao de Documento de Requisitos de Produto (PRD), planejamento de capacidade de sprints, abertura e sincronizacao de tarefas em rastreadores de pendencias, inteligencia de codigo baseada em AST, GraphRAG multicamadas, execucao de pipelines agilicos, geracao automatica de testes e melhoria continua.

---

## Visao Geral da Arquitetura

O `faccoder` e estruturado como um monorepositorio Python modular, contendo pacotes instalaveis no diretorio `packages/`:

```
faccoder/
├── packages/
│   ├── core/           # Registro de LLMs, telemetria Langfuse, busca hibrida, sqlite-vec
│   ├── code-intel/     # Analisadores AST (tree-sitter, Delphi), CodeGraph, GraphRAG, HyDE
│   ├── agents/         # Catalogo de personas (100+ agentes), motor de pipelines LangGraph
│   └── planning/       # Decomposicao de PRD, planejamento de capacidade, sync idempotente
├── docs/               # Guias aprofundados de arquitetura e documentacao de referencia
└── scripts/            # Utilitarios de auditoria de qualidade e formatacao
```

### Pacotes Principais (Disponiveis na Branch Develop)

1. **`faccoder-core`**: A base compartilhada por todos os componentes da plataforma.
   - Registro de modelos por camadas (`small`, `medium`, `large`), abstraindo provedores pagos (Anthropic, OpenAI, Google Gemini, Azure, Bedrock) e de codigo aberto (Ollama, vLLM, LM Studio, llama.cpp).
   - Rastreamento resiliente via Langfuse com disjuntor automatico (circuit breaker), degradando para operacao neutra (no-op) se o servidor de telemetria estiver inacessivel.
   - Medicao de consumo e custo por agente, pipeline e execucao, com limites orcamentarios estritos.
   - Chamadas estruturadas (`call_structured`) validadas contra esquemas Pydantic, com retentativa corretiva automatica em caso de falha de validacao.
   - Repositorio local de busca hibrida integrando SQLite FTS5 (busca lexica BM25) com `sqlite-vec` (vetores densos), fusao por postos reciprocos (RRF) e reordenacao por cross-encoder.
   - Sandbox de caminhos de arquivos para prevencao de navegacao indevida no sistema de arquivos.

2. **`faccoder-code-intel`**: Inteligencia de codigo e compreensao semantica de repositorios.
   - Analisadores sintaticos AST baseados em Tree-sitter (Python, Go, JavaScript, TypeScript, Java, C, C++, Rust) e analisador dedicado para Object Pascal / Delphi.
   - Divisao de codigo (chunking) baseada em simbolos sintaticos, preservando o contexto de escopo.
   - `CodeGraph` com modelagem de relacoes: chamadas, heranca, implementacao de interfaces e associacoes de telas visuais (DFM).
   - Deteccao de comunidades arquiteturais via modularidade Louvain (GraphRAG), permitindo sinteses hierarquicas do sistema.
   - Transformacao de consultas com HyDE (Hypothetical Document Embeddings) e geracao recursiva de documentacao de baixo para cima.

3. **`faccoder-agents`**: Catalogo de personas e motor de execucao de agentes.
   - Catalogo formal com metadados em frontmatter YAML (`agents/<sector>/<slug>.md`), cobrindo 10 setores organizacionais (diretoria, requisitos, produto, engenharia, UI/UX, qualidade/QA, seguranca, dados/IA, suporte e marketing).
   - Blocos modulares reutilizaveis para LangGraph: `ValidatorBlock`, `ConditionBlock`, `PromptBlock` e `HumanApprovalBlock`.
   - Garantias operacionais de seguranca: execucao simulada (dry-run), fichas de aprovacao com tempo limite, tetos de execucao de ferramentas e votacao por quorum em comite.
   - Exportadores para criacao de pacotes de subagentes e ferramentas compativeis com Claude Code.

4. **`faccoder-planning`**: Planejamento agil de sprints e sincronizacao de tarefas.
   - Decomposicao de PRDs em Epicos, Historias de Usuario e Tarefas tecnicas com criterios de aceitacao no formato Dado/Quando/Entao.
   - Calculadora de capacidade de sprints considerando disponibilidade real, margem de reserva e velocidade historica da equipe.
   - Laco de sincronizacao de quadros Kanban, identificando riscos de atraso e sugerindo adiamentos estrategicos.
   - Adaptadores idempotentes para plataformas (GitHub Issues, Milestones, Projects v2 GraphQL, GitLab e Azure DevOps) com marcadores ocultos de rastreamento (`<!-- faccoder-id: <uuid> -->`).
   - Automatizacao de operacoes Git: criacao de branches, formatacao de commits convencionais e abertura de pull requests com verificacao integrada.

---

## Guia Rapido

### Instalacao

Instale os pacotes principais do workspace em modo editavel:

```bash
# Clone o repositorio
git clone https://github.com/ThiagoVenturim/faccoder.git
cd faccoder

# Crie e ative o ambiente virtual
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Instale os pacotes principais
pip install -e packages/core
pip install -e packages/code-intel
pip install -e packages/agents
pip install -e packages/planning
```

### Invocacao Basica de Modelos

```python
from faccoder_core import get_chat_model, load_config

# Carrega as configuracoes a partir de variaveis de ambiente ou arquivo
config = load_config()

# Obtem o modelo configurado para o nivel intermediario ('medium')
model = get_chat_model("medium", config=config)

resposta = model.invoke("Resuma os principios fundamentais de um sistema RAG em producao.")
print(resposta.content)
```

### Indexacao de Codigo e Busca Hibrida

```python
from faccoder_code_intel import CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder

# Inicializa o indice com representacoes vetoriais e busca lexica SQLite FTS5
embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("indice_codigo.db", embedder=embedder)

# Indexa rotinas ou arquivos de codigo
index.index_code("servico_auth.py", "def autenticar_usuario(token): ...", language="python")

# Executa busca com sintese de resposta hipotetica (HyDE) e fusao RRF
resultados = index.search("validacao de sessao de usuario", top_k=3, hyde=True)
for item in resultados:
    print(f"[{item['score']:.3f}] {item['id']}: {item['text']}")
```

---

## Predefinicoes de Execucao (Presets)

O `faccoder` permite selecionar o modo de execucao dos modelos por meio do parametro `preset` em `FaccoderConfig`:

- `offline`: Utiliza `FakeChatModel` e calculo de embeddings deterministico, permitindo execucao completa de testes sem rede ou custos.
- `all-open-source`: Direciona todas as camadas para instancias locais do Ollama ou vLLM.
- `local-vllm`: Servidores vLLM locais de alto desempenho com paralelismo de tensores.
- `all-paid`: Utiliza modelos de ponta (Anthropic Claude, OpenAI e Google Gemini) distribuidos conforme a complexidade.
- `hybrid`: Encaminha tarefas volumosas (extracao, classificacao, chunking) para modelos locais e tarefas de raciocinio complexo (comite, arquitetura, sintese) para modelos proprietarios de alta capacidade.

---

## Indice de Documentacao

Guias detalhados estao disponiveis no diretorio [docs/](docs/):

- **Fundamentos e Infraestrutura**:
  - [Primeiros Passos](docs/getting-started.md): Instalacao, configuracao de ambiente e preparacao de espacos de trabalho.
  - [Arquitetura](docs/architecture.md): Estrutura do monorepositorio, fluxo de dados e limites entre pacotes.
  - [Modelos: Codigo Aberto vs Proprietarios](docs/models-open-vs-paid.md): Comparacao de modelos, mapeamento por camadas e compensacoes de custo.
  - [Execucao Local: vLLM vs Ollama](docs/serving-vllm-vs-ollama.md): Dimensionamento de hardware, benchmarks de concorrencia e conteineres.
  - [Observabilidade com Langfuse](docs/observability-langfuse.md): Rastreamento de traces, controle de custos, disjuntor e metricas.
  - [Plano de Controle](docs/control-plane.md): Orcamento por chave de API, controle de taxas, auditoria e governanca humana.

- **Ideacao, Planejamento e Agentes**:
  - [Ideacao e Comite](docs/ideation-and-jury.md): Esquadrao de pesquisa de mercado, matriz competitiva e votacao por quorum.
  - [Planejamento Agilico](docs/agentic-planning.md): Conversao de PRD, gestao de capacidade de sprint e sincronizacao idempotente de tarefas.
  - [Catalogo de Agentes](docs/agents-catalog.md): Taxonomia de personas, esquema de metadados e pacotes por tecnologia.
  - [Pipelines](docs/pipelines.md): Orquestracao de fluxos LangGraph, blocos reutilizaveis e portais de aprovacao humana.

- **Inteligencia de Codigo, Recuperacao e Estudo de Caso**:
  - [Fundamentos de RAG](docs/rag-fundamentals.md): Busca lexica, representacoes vetoriais, tecnicas de fragmentacao e fusao hibrida.
  - [RAG Avancado](docs/advanced-rag.md): Expansao de consultas, HyDE, diversificacao MMR, compressao contextual e fusao RRF.
  - [GraphRAG](docs/graphrag.md): Grafos de relacoes de codigo, deteccao de comunidades por modularidade Louvain e sintese em multiplos saltos.
  - [Reordenacao (Reranking)](docs/reranking.md): Cross-encoders, bi-encoders, latencia de inferencia e pipelines de recuperacao em duas fases.
  - [Selecao de Modelos de Embeddings](docs/choosing-embedding-models.md): Comparacao tecnica (BGE-M3, Nomic, Voyage, OpenAI) e dimensionalidade.
  - [Suporte a Linguagens](docs/languages.md): Gramaticas Tree-sitter, analisadores de Object Pascal / Delphi e extracao de simbolos.
  - [Estudo de Caso](docs/case-study.md): Como um sistema corporativo monolitico legado com 20 anos de desenvolvimento foi completamente mapeado e documentado em tres semanas.

---

## Padroes de Desenvolvimento do Repositorio

Qualquer contribuicao para o `faccoder` deve cumprir os seguintes padroes automatizados:

1. **Zero Emojis**: E terminantemente proibido o uso de emojis em codigo, comentarios, mensagens de commit, documentacao Markdown ou textos de interface. Validado por `scripts/check_no_emoji.py` e githooks.
2. **Zero Linhas de Co-Autoria por IA**: Commits nao devem conter linhas de atribuicao automatica (`Co-Authored-By:`). O hook `.githooks/commit-msg` remove tais linhas automaticamente.
3. **Commits Convencionais Padronizados**: Mensagens de commit devem seguir o padrao Conventional Commits em ingles (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
4. **Testes Hermeticos Offline**: As suites de testes devem passar sem dependencia de conexao de rede ou credenciais externas pagas, utilizando o preset `offline` e modelos simulados.
5. **Auditoria de Codigo e Formatacao**: O codigo deve cumprir integralmente as diretrizes do Ruff.

---

## Origem

O `faccoder` tem sua origem em sistemas corporativos de inteligencia artificial aplicados em larga escala concebidos por Thiago Venturim:

- **ApoIA**: Plataforma corporativa interna validada em producao com mais de 100 agentes autonomos, 11 habilidades especializadas e sistemas legados com milhoes de linhas de codigo.
- **lochome**: Framework de engenharia cobrindo mais de 70 personas tecnicas especializadas, modelos de capacidade e sincronizacao automatizada de desenvolvimento.

Os aprendizados, mecanismos de busca semantica e padroes de governanca desses projetos foram consolidados no `faccoder` como uma plataforma aberta, generica e independente de fornecedor.

---

## Licenca

Este projeto e distribuido sob os termos da [Licenca MIT](LICENSE).
