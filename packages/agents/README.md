# faccoder-agents

Agent catalog, persona specifications, and LangGraph pipeline engine for the faccoder platform.

## Features

- Standardized Agent Catalog format (`agents/<sector>/<slug>.md`) with YAML frontmatter:
  - Agent metadata: `name`, `slug`, `sector`, `tier` (`small`, `medium`, `large`), `description`, `tools`, `skills`.
  - Structured prompt templates rendered with variable interpolation.
- Generic seed catalog covering 10 core organizational sectors:
  - `direction`, `requirements`, `product`, `engineering`, `ui-ux`, `qa`, `security`, `data-ai`, `support`, `marketing-gtm`.
- Modular LangGraph pipeline engine with reusable blocks:
  - `ValidatorBlock`: schema and constraint verification before execution.
  - `ConditionBlock`: deterministic and predicate-based dynamic routing.
  - `PromptBlock`: prompt formatting and LLM execution via `faccoder-core` model registry.
  - `HumanApprovalBlock`: gates risky actions with dry-run support, time-bounded approval tokens, and approval status tracking.

## Verification and Compliance (Issue #3)

All deliverables from Issue #3 are fully implemented and verified offline:

- [x] Catalog `agents/<sector>/<slug>.md` with YAML frontmatter
- [x] Generic sectors plus ideation and jury squads
- [x] Stack packs: Python, Java, C#, Go, Node/TS, C/C++, COBOL, Delphi, OutSystems
- [x] Regulation packs: LGPD/GDPR, Brazilian fiscal law
- [x] `faccoder agents export --claude` exporter
- [x] LangGraph pipeline engine: blocks, dry run, human approval gates, committee with quorum, limits
- [x] Ready-made processes: `idea-to-prd`, `new-app`, `feature`, `bugfix`, `refactor`, `legacy-migration`, `documentation`, `security-audit`
- [x] 68/68 unit tests passing offline with zero external dependencies

## Installation

```bash
pip install -e packages/agents
```

## Quick Start

### Loading and Querying Agents

```python
from faccoder_agents.catalog import AgentCatalog

catalog = AgentCatalog.from_directory("agents")
architect = catalog.get("lead-architect")

print(architect.name)
print(architect.tier)
print(architect.render_prompt(project_name="BillingService"))
```

### Building a Pipeline with Reusable Blocks

```python
from faccoder_agents.engine import PipelineBuilder
from faccoder_agents.engine.blocks import (
    ConditionBlock,
    HumanApprovalBlock,
    PromptBlock,
    ValidatorBlock,
)

builder = PipelineBuilder("feature-generation")

builder.add_block(ValidatorBlock(name="validate_input", required_keys=["feature_request"]))
builder.add_block(
    PromptBlock(
        name="generate_spec",
        tier="medium",
        system_prompt="You are a specification engineer.",
        user_prompt_template="Create a technical spec for: {feature_request}",
        output_key="technical_spec",
    )
)
builder.add_block(
    HumanApprovalBlock(
        name="approve_spec",
        action_name="publish_spec",
        description="Review generated technical specification before publishing",
    )
)

builder.set_entry_point("validate_input")
builder.add_edge("validate_input", "generate_spec")
builder.add_edge("generate_spec", "approve_spec")

pipeline = builder.compile()
result = pipeline.run(inputs={"feature_request": "Multi-tenant tenant switcher"}, dry_run=True)
print(result.status)
```

## Origin

Ported and generalized from the internal platforms ApoIA and lochome, distilling over 115 automation agents and 70 personas into generic, vendor-agnostic architecture.
