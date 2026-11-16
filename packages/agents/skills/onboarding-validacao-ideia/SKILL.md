---
name: onboarding-validacao-ideia
description: Conduz o onboarding e lapidacao para novos projetos e ideias do zero (Persona B), questionando hipoteses, mercado, orcamento e alimentando pesquisa e juri.
user-invocable: true
---

# Onboarding Guiado - Persona B: Validacao de Ideia e Concepcao do Zero

Metodologia de descoberta e estruturacao para empreendedores, times e inovadores que possuem apenas uma ideia inicial ou dor de mercado, sem codigo preexistente.

## Contexto e Dores Tipicas da Persona B

- Dificuldade para saber por onde comecar e como estruturar o projeto.
- Incerteza se a ideia possui mercado real e clientes dispostos a pagar.
- Receio de custos elevados e desperdicio financeiro antes da validacao.
- Ausencia de equipe tecnica formada ou de especialistas de tecnologia.
- Indefinicao de escopo, prazos viaveis e preco de desenvolvimento.
- Necessidade imperativa de validar hipoteses antes de iniciar a construcao de software.

## Roteiro de Entrevista Guiada (Persona B)

O NexCoder atua questionando a ideia para lapidar o escopo e identificar riscos:

1. **Problema Central e Dor**:
   - Qual e a dor especifica que se quer solucionar e como ela e tratada hoje.
   - Fornece o ponto de partida para o levantamento de lacunas de mercado.

2. **Publico-Alvo e Cliente Ideal**:
   - Segmento, perfil demografico ou operacional e escala do cliente potencial.
   - Orienta a analise de mercado total e servivel (TAM, SAM, SOM).

3. **Diferencial e Proposta de Valor**:
   - Qual e a vantagem competitiva frente a solucoes substitutas ou concorrentes diretos.
   - Alimenta a matriz de diferenciacao competitiva.

4. **Orcamento e Investimento Pretendido**:
   - Faixa de investimento disponivel para construcao, lancamento e sustentacao inicial.
   - Permite adequar o escopo do MVP a realidade financeira.

5. **Prazo e Cronograma Desejado**:
   - Horizonte temporal esperado para colocar o primeiro piloto operacional no ar.
   - Base para a divisao em sprints e capacidade produtiva.

6. **Riscos e Premissas a Validar**:
   - Principais duvidas ou hipoteses criticas que precisam ser comprovadas.
   - Baliza a deliberacao do comite de juri.

## Integracao com a Esteira NexCoder

O perfil consolidado (`ScenarioProfile`) direciona os seguintes passos autonomos:
- `research-squad`: Investigacao profunda de mercado, competidores, lacunas e precificacao.
- `jury-committee`: Deliberacao formal com 6 personas emitindo veredito (go, pivot ou no-go).
- `prd-generator`: Sintese do documento de requisitos de produto formal.
- `cost-calculator`: Estimativa detalhada de custos de construcao, infraestrutura e manutencao.
- `mvp-iac-scaffolding`: Criacao do repositorio inicial, estrutura de codigo, testes e IaC.
