# Ideation and Jury: From Concept to PRD

Software projects often fail before writing code due to flawed market assumptions, unnoticed competitors, or unvetted technical risks.

The `faccoder` ideation subsystem automates the front of the software lifecycle: turning an unstructured idea into an evidenced Product Requirement Document (PRD) vetted by an automated multi-persona jury.

---

## The Four-Stage Ideation Lifecycle

```
[Raw Idea]
    |
    v
+------------------------+
| 1. Intake              | -> Extract problem statement, audience, value hypothesis
+-----------+------------+
            |
            v
+------------------------+
| 2. Research Squad      | -> Autonomous market, competitor, differentiator & gap analysis
+-----------+------------+
            |
            v
+------------------------+
| 3. Architectural Jury  | -> Multi-persona committee scoring against standardized rubric
+-----------+------------+
            |
            +-- [PIVOT / NO-GO] -> Loop back with feedback & mitigation recommendations
            |
            v [GO]
+------------------------+
| 4. PRD & Arch Proposal | -> Actionable requirements ready for agentic sprint planning
+------------------------+
```

---

## 1. Intake Stage: Structuring the Hypothesis

The user provides a high-level proposal or problem statement in natural language. The `idea-analyst` agent structures the proposal into core dimensions:

- **Target Persona & User Segment**: Who experiences this friction?
- **Core Pain Point**: What is the root failure of current workarounds?
- **Value Hypothesis**: What quantifiable metric improves if this problem is resolved?
- **Proposed Solution Model**: Initial technical architecture or product direction.

---

## 2. The Autonomous Research Squad

Once structured, the proposal triggers a parallel research squad of specialized personas:

| Agent Persona | Focus Area | Research Output |
|---|---|---|
| `market-researcher` | Market TAM/SAM, adoption trends, economic drivers | Market size estimates, regulatory headwinds, macroeconomic factors |
| `competitor-scout` | Direct and indirect competitors | Matrix of existing tools, pricing tiers, market share, and target niches |
| `differentiator-analyst` | Feature parity vs unique competitive moat | Gap analysis table identifying table-stakes vs killer features |
| `gap-hunter` | User complaints, negative reviews, forum friction | Unresolved issues in competitor products (bugs, pricing spikes, missing APIs) |
| `user-voice` | Synthetic persona interviews | Evidence-backed user stories and operational constraints |
| `pricing-strategist` | Monetization models | Packaging tiers (open-source core vs hosted cloud, usage billing vs seat licenses) |

Every factual assertion must cite verifiable sources or specify that it is an inferred model projection.

---

## 3. The Architectural Jury (Committee with Quorum)

Once the research dossier is compiled, it is submitted to the **Jury**—a committee of diverse personas evaluating the proposal from conflicting perspectives:

```
+--------------------------------------------------------------+
|                    Jury Committee Personas                   |
+--------------------------------------------------------------+
| 1. The Investor:       Unit economics, market size, ROI      |
| 2. The CTO:            Technical feasibility, scalability, risk|
| 3. The End User:       Workflow ergonomics, time-to-value    |
| 4. The Security Lead:  Attack surface, privacy, compliance   |
| 5. The Devil's Advocate: Structural flaws, existential risks |
+--------------------------------------------------------------+
```

### Evaluation Rubric

Each juror assigns scores (1 to 5) across six standardized criteria:

1. **Problem Severity**: Is this a genuine pain point or a manufactured solution?
2. **Market Opportunity**: Is the addressable market viable for the required investment?
3. **Competitive Differentiation**: Does the product possess a defensible advantage?
4. **Technical Feasibility**: Can the architecture be delivered within reasonable complexity?
5. **Operational & Security Risk**: Are legal, regulatory, or operational vulnerabilities manageable?
6. **Cost-to-Value Ratio**: Does the expected return justify the infrastructure and development budget?

### Quorum and Verdicts

- **GO**: Weighted average score exceeds threshold (e.g. >= 4.0 / 5.0) with no individual category veto (no score of 1). The proposal advances immediately to PRD generation.
- **PIVOT**: The core value proposition is acknowledged, but specific architectural, security, or pricing flaws are flagged. The jury outputs concrete pivot requirements, and the squad re-runs research focusing on those areas.
- **NO-GO**: The proposal is judged fundamentally non-viable, unfeasible, or economically flawed. Detailed rationales are logged to prevent repeated wasted effort.

---

## 4. PRD and Architecture Proposal Generation

Upon achieving a `GO` verdict, `faccoder` synthesizes the squad findings and jury recommendations into an actionable **Product Requirement Document (PRD)**:

- **Executive Summary & Value Proposition**
- **Non-Functional Requirements**: Latency budgets, concurrency targets, security isolation, and compliance rules.
- **Functional Requirements & User Journeys**
- **Architectural Proposal**: Monorepo packages, service boundaries, data schemas, and API contracts.
- **Human Approval Gate (b85)**: The complete PRD is presented to the engineering lead for review. Once confirmed, it is handed directly to `faccoder-planning` for sprint task decomposition.
