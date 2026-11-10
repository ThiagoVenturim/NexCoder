---
name: technical-planning
description: Decompose architectural initiatives and epics into realistic technical stories, tasks, hour estimates, dependencies, and sprint capacity plans.
user-invocable: true
---

# Technical Planning and Estimation

Methodology for translating architectural findings and product epics into executable engineering backlogs with `nexcoder-planning`.

## Decomposition Guidelines

1. **Epic to Story to Task Hierarchy**
   - Group related architectural and quality actions into cohesive Epics (`EP-XX`) and User/Engineering Stories (`US-XX`).
   - Break each story into concrete technical Tasks (`TSK-XX`) scoped between 1 and 8 ideal engineering hours.

2. **Task Metadata & Dependencies**
   - Assign each task a target `layer` (`core`, `backend`, `frontend`, `data`, `qa`, `devops`, `security`), realistic `estimate_hours`, and `recommended_agent`.
   - Declare explicit task dependencies (`dependencies: ["TSK-01"]`) so prerequisite refactors and domain models precede dependent adapters and tests.

3. **Testable Acceptance Criteria**
   - Specify deterministic `Given / When / Then` acceptance criteria for every task so verification can be automated.

4. **Capacity-Aware Sprint Scheduling**
   - Schedule tasks against team availability and focus factor using `CapacityCalculator` to prevent sprint overcommitment.
