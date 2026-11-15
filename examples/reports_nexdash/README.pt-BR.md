# Dashboards de Produtividade e Seguranca via NexDash (Exemplo Offline)

Este exemplo roda 100% offline com dados sinteticos deterministas para gerar dois dashboards HTML e relatorios JSON usando o `nexdash` como motor:

1. **Produtividade de Engenharia (`dev_productivity`)**: coleta dados normalizados de PRs, tempo de code review, lead time e issues fechadas do GitHub, Azure DevOps e Redmine (`nexcoder-planning`) e envia ao `nexdash` via **MCP (JSON-RPC 2.0)**.
2. **Postura de Seguranca (`security_posture`)**: consolida vulnerabilidades dos scanners (`semgrep`, `bandit`, `gitleaks`, `osv-scanner`, `pip-audit`, `trivy`, `syft`), dependencias desatualizadas no SBOM e cobertura do gate de release (`nexcoder-security`), enviando ao `nexdash` via **REST (`POST /v1/reports/generate`)**.

## Como executar

Na raiz do repositorio:

```bash
python examples/reports_nexdash/run_reports_demo.py --output-dir ./artifacts-relatorios
```

Arquivos gerados:

- `productivity_dashboard.html`: dashboard HTML com `Content-Security-Policy` (`connect-src 'none'`) e dados injetados em `window.NEXDASH_DATA`.
- `productivity_report.json`: metricas calculadas (PRs abertos/mesclados, tempo medio e mediano de review, lead time, issues fechadas e entregas por pessoa).
- `security_dashboard.html`: dashboard HTML com vulnerabilidades por severidade, tendencia semanal e cobertura dos scanners no gate.
- `security_report.json`: metricas estruturadas de seguranca e pacotes com atualizacao recomendada.

## Rodar os testes

```bash
python -m pytest examples/reports_nexdash/tests/test_reports_demo.py
```
