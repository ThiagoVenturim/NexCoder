# Referencias e diferencial do nexcoder

Projetos parecidos (open source e privados), o diferencial do nexcoder e o que da para melhorar com base neles. Pesquisa de 2026-11-08; verifique cada projeto antes de usar como referencia.

## Parecidos

### Open source
- **OpenHands** (ex-OpenDevin): agente autonomo que decompoe tarefas complexas em subtarefas e delega a subagentes; MIT. O mais proeminente alternativo ao Devin.
- **SWE-agent** (Princeton): agente para resolver issues, voltado a pesquisa e self-host.
- **Devika**: alternativa open source ao Devin.
- **MetaGPT**: framework multi-agente (papeis de empresa de software) mais antigo.
- **AutoCodeRover**: automacao de correcao de bug.
- **Aider / Continue** (assistentes de codigo) cobrem partes do fluxo (edicao guiada por IA).

### Privados / fechados
- **Devin (Cognition)**: engenheiro de software autonomo, referencia do genero.
- **GitHub Copilot Workspace**, **Cursor**, **Factory**, **Lovable/Bolt**: cobrem partes (planejar, editar, gerar app) de forma fechada.

## Nosso diferencial
- **Esteira completa, nao so "escrever codigo"**: ideia -> squad de pesquisa -> juri (go/pivot/no-go) -> PRD -> sprints em git -> codigo -> captura e testes -> seguranca -> release -> melhoria continua.
- **Code intelligence forte**: AST/symbols, CodeGraph, GraphRAG com deteccao de comunidades e documentacao bottom-up, em varias linguagens (inclui Delphi; C/C++/Java/Go/JS/TS/Rust/Python).
- **Escolha de modelo por nivel** (aberto ou pago) via nexcoder-core, com Langfuse, cache e orcamento; roda offline com preset offline.
- **Control plane** proprio: chaves, custo, orcamento e auditoria.
- **Politica de uso etica + gate**: so alvo proprio/autorizado, divulgacao responsavel (ver USAGE_POLICY planejada, issue #74). MIT de verdade.
- **Modo open source** (issue #75): analisar projeto, achar melhorias e contribuir com responsabilidade.

## O que melhorar aprendendo com eles
- **Benchmark publico** (SWE-bench como OpenHands/SWE-agent usam): medir e publicar numeros para dar credibilidade.
- **Sandbox de execucao** robusto (OpenHands roda em runtime isolado): reforcar o ambiente efemero para rodar e testar com seguranca.
- **Catalogo real e honesto de agentes**: a auditoria (#66) ja ajustou a contagem; seguir enxugando o que nao agrega (ver issues #80/#81 de qualidade).
- **Onboarding em minutos** (Cursor/Aider sao faceis de comecar): o quickstart offline (#64) ajudou; faltam exemplo gravado e docs navegaveis (mkdocs).
- **Integracao com editor/IDE** (Copilot/Cursor): expor o nexcoder dentro do editor, nao so CLI/MCP.
- **Marketplace de pipelines/skills** ajustaveis, como varios frameworks multi-agente oferecem.

## Sources
- https://www.e2b.dev/blog/open-source-alternatives-to-devin
- https://github.com/e2b-dev/awesome-devins
- https://toolhalla.ai/blog/devin-vs-openhands-vs-swe-agent-2026
- https://alternativeto.net/software/devin/
