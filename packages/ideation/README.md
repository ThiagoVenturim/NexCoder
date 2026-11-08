# faccoder-ideation

Ideation, research squad, and jury committee package for faccoder: transforms free-text product ideas into rigorous, verified Product Requirement Documents (PRDs) and system architecture proposals through autonomous multi-agent diligence and human governance gates.

## Features

- **Intake & Structuring**:
  - `IdeaAnalyst` structures free-text brainstorms into clear problem statements, target audience segments, and value hypotheses.
  - Generates initial assumptions and domain tagging.
- **Multi-Agent Research Squad**:
  - 7 specialized research agents running in parallel or sequentially:
    - `MarketResearcher`: Total addressable market (TAM, SAM, SOM), CAGR, and growth drivers.
    - `CompetitorScout`: Direct and indirect incumbent profiling and feature tracking.
    - `DifferentiatorAnalyst`: Feature differentiation matrix, defensibility factors, and positioning.
    - `GapHunter`: Unaddressed customer complaints, forum discussions, and market voids.
    - `UserVoiceResearcher`: Synthetic personas with empirical evidence and interview simulations.
    - `PricingResearcher`: SaaS monetization models, willingness-to-pay, and tier design.
    - `LegalPrivacyResearcher`: Regulatory compliance (GDPR, CCPA, EU AI Act), data sovereignty, and IP risk.
  - Pluggable search providers with offline mock fallbacks and citations attached to every claim.
- **b90 Jury Committee**:
  - 6 juror personas: `investor`, `cto`, `end-user`, `security`, `market`, and `devil-advocate`.
  - Public rubric covering 6 evaluation criteria: problem, market, differentiation, feasibility, risk, and cost.
  - Quorum-based voting mechanism producing consensus decisions: `go`, `pivot`, or `no-go`.
  - Support for multi-round refinement and re-evaluation cycles.
- **Deliverables & b85 Governance Gate**:
  - Generates standard Markdown PRD directly compatible with `faccoder-planning`.
  - Comprehensive Markdown and self-contained responsive HTML executive reports.
  - Modular system architecture proposal with component breakdown and security controls.
  - Cryptographic b85 human approval gate with 30-minute token expiration before advancing to sprint planning.

## Installation

```bash
pip install -e packages/ideation
```

## Quick Start

```python
from faccoder_ideation import IdeationPipeline

# Initialize pipeline (100% offline with mock search provider)
pipeline = IdeationPipeline(allow_network=False)

# Run idea intake and research
idea_text = "Autonomous security compliance scanning tool for Kubernetes clusters that opens fix PRs."
output, approval_secret = pipeline.run(idea_text)

print(f"Idea: {output.structured_idea.title}")
print(f"Jury Verdict: {output.jury_verdict.verdict.value.upper()}")
print(f"Average Rubric Score: {output.jury_verdict.average_scores}")

# Authorize human gate before planning handoff
pipeline.approve_gate(output, token_or_secret=approval_secret, approver="alice")
print(f"Gate Approved: {output.approval_gate.approved}")

# Save deliverables to disk
files = pipeline.save_deliverables(output, "output_artifacts")
print(f"Generated PRD: {files['prd']}")
```

## Origin

A modular, open-source architecture for research and multi-agent pipelines.
