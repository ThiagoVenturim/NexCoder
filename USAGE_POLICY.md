# Ethical Usage Policy / Politica de Uso Etica

`nexcoder` is distributed under the [MIT License](LICENSE). We keep the license open source and enforce ethical boundaries through project policy and code-level guardrails rather than license restrictions.

---

## English

### 1. Defensive and Constructive Purpose

Use `nexcoder` to protect websites and applications, contribute to open-source projects, and improve software engineering quality. Never use `nexcoder` to cause harm, disrupt services, exfiltrate data, or attack third-party systems.

### 2. Owned or Explicitly Authorized Targets Only

Run automated tests, web or desktop captures, and security scans only against targets you own or targets for which you hold explicit written authorization from the owner.

- Local repositories and staging environments under your control must be marked as owned targets before running scans.
- External domains, APIs, or applications require documented authorization from the asset owner.
- Bypassing authentication controls, rate limits, or CAPTCHA challenges is prohibited.

### 3. Coordinated Vulnerability Disclosure

When a scan or review uncovers a security flaw in third-party or open-source software, follow coordinated disclosure:

- Report the issue privately through the maintainer's official security channel (see [SECURITY.md](SECURITY.md) or GitHub Private Vulnerability Reporting).
- Give maintainers reasonable time to release a fix before any public discussion.
- Do not publish working exploits, weaponized payloads, or offensive proof-of-concept (PoC) scripts.

### 4. Code-Level Gate (`nexcoder-control`)

`nexcoder` enforces this policy in code through `nexcoder-control` (`TargetAuthorizationGate`, `ApprovalTokenManager`, and `AppendOnlyAuditLog`):

- Any mode that runs security scans or automated target checks requires the target to be marked as owned (`owned_target=True` or registered in `TargetAuthorizationGate`) or backed by an approval token.
- Every scan or test authorization — and every refusal — is recorded in the tamper-evident `AppendOnlyAuditLog` with the authorizing actor, UTC timestamp, target identifier, and execution mode.
- Secrets, tokens, and credentials are redacted before any event is written to the audit log.
- If a target is not marked as owned or authorized, `nexcoder` refuses execution and explains how to register authorization.

---

## Portugues (pt-BR)

O `nexcoder` e distribuido sob a [Licenca MIT](LICENSE). O projeto permanece open source de verdade: a regra etica entra como politica publica e bloqueio tecnico no codigo, nao como restricao na licenca.

### 1. Uso para Proteger e Construir

Use o `nexcoder` para proteger sites e aplicacoes, contribuir com projetos de codigo aberto e melhorar a qualidade de software; nunca para o mal, interrupcao de servicos, coleta indevida de dados ou ataque a terceiros.

### 2. Testes e Varreduras Somente em Alvo Proprio ou Autorizado

Execute testes automatizados, capturas web/desktop e varreduras de seguranca apenas contra alvos proprios ou com autorizacao explicita do dono do ativo.

- Repositorios locais, ambientes de homologacao e aplicacoes sob sua responsabilidade devem ser marcados como alvo proprio antes da varredura.
- Dominios, APIs ou sistemas de terceiros exigem autorizacao previa e documentada do proprietario.
- E proibido contornar mecanismos de autenticacao, limites de requisicao ou desafios CAPTCHA.

### 3. Divulgacao Responsavel (Coordinated Disclosure)

Falhas de seguranca encontradas em projetos de terceiros ou open source seguem divulgacao responsavel:

- Relate a falha em canal privado oficial do projeto (como [SECURITY.md](SECURITY.md) ou o relato privado de vulnerabilidades do GitHub).
- Aguarde um prazo razoavel para que os mantenedores publiquem a correcao antes de divulgar detalhes tecnicos.
- Nao publique exploits funcionais, cargas ofensivas nem provas de conceito (PoC) voltadas a exploracao.

### 4. Gate no Codigo (`nexcoder-control`)

O `nexcoder` aplica esta politica diretamente no codigo reusando o plano de controle `nexcoder-control` (`TargetAuthorizationGate`, `ApprovalTokenManager` e `AppendOnlyAuditLog`):

- Qualquer modo que execute testes ou varreduras exige o alvo marcado como proprio (`owned_target=True` ou registrado no `TargetAuthorizationGate`) ou uma ficha de aprovacao valida.
- O gate grava no log de auditoria encadeado (`AppendOnlyAuditLog`) quem autorizou, quando (timestamp UTC) e qual alvo foi avaliado.
- Segredos, chaves e tokens sao ocultados antes de qualquer gravacao em log.
- Sem a marca de alvo proprio ou autorizacao registrada, o `nexcoder` recusa a execucao e explica o motivo.
