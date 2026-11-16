---
name: onboarding-empresa-produto
description: Conduz o onboarding guiado para empresas estruturadas com produto e codebase existentes (Persona A), levantando stack, dores de legado, infra e alimentando a esteira de modernizacao.
user-invocable: true
---

# Onboarding Guiado - Persona A: Empresa e Produto Existente

Metodologia de descoberta e onboarding para organizacoes que possuem sistemas em producao, codigo legado e infraestrutura estabelecida.

## Contexto e Dores Tipicas da Persona A

- Codigo legado e dividas tecnicas acumuladas ao longo dos anos.
- Custos de nuvem e manutencao sem visibilidade ou previsibilidade.
- Inseguranca e medo de quebrar funcionalidades em deploys.
- Ausencia ou fragilidade em testes automatizados e observabilidade.
- Riscos de seguranca da informacao e conformidade regulatoria (LGPD).
- Dependencia critica de poucas pessoas que conhecem o sistema.
- Dificuldade para documentar e acelerar o onboarding de novos desenvolvedores.
- Demanda por novas entregas sem degradar o ambiente produtivo.

## Roteiro de Entrevista Guiada (Persona A)

A pessoa relata o cenario atual e o NexCoder formula perguntas essenciais:

1. **Stack Tecnologica e Arquitetura**:
   - Linguagens, frameworks, bancos de dados e runtime.
   - O NexCoder utiliza essas definicoes para orientar o analisador sintatico do code-intel.

2. **Hospedagem e Infraestrutura**:
   - Onde o sistema esta hospedado (AWS, Azure, GCP, bare-metal, containers, serverless).
   - Base para estimativa de custos e sugestoes de IaC.

3. **Dores Tecnicas e Gargalos**:
   - Falta de testes, custos excessivos, lentidao, bugs recorrentes ou divida tecnica.
   - Direciona a priorizacao dos agentes de qualidade e refatoracao guiada.

4. **Metas de Curto e Medio Prazo**:
   - Modernizacao, reducao de custos, adicao de features, escalabilidade.
   - Sintoniza o plano de entregas com o retorno financeiro.

5. **Restricoes e Conformidade**:
   - Requisitos de LGPD, janelas de manutencao e contratos de nivel de servico (SLA).
   - Configura as politicas de governanca e guardrails.

6. **Acesso ao Codigo e Infraestrutura**:
   - Permissao formal para inspecao automatizada sob gate de seguranca assinado.
   - Com autorizacao, o NexCoder indexa o codigo e extrai documentacao bottom-up.

## Integracao com a Esteira NexCoder

O perfil gerado (`ScenarioProfile`) ativa automaticamente os seguintes modulos:
- `code-intel/GraphRAG`: Indexacao do grafo de chamadas, dependencias e simbolos.
- `quality-agents`: Identificacao de duplicidades, over-engineering e code smells.
- `security-audit-gate`: Auditoria estatica autorizada com gate criptografico.
- `cost-calculator`: Estimativa de custos operacionais e economias potenciais.
- `architecture-refactor`: Propostas de refatoracao com testes de caracterizacao e PRs incrementais.
