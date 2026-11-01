# Case Study: Documenting a 20-Year Legacy Monolith in 3 Weeks

Enterprise software organizations frequently maintain core mission-critical systems that have evolved over two decades. Over time, original authors depart, architectural documentation becomes obsolete or lost, and onboarding a new software engineer takes six to nine months.

This case study documents how the techniques and architecture now packaged in `faccoder` were deployed against a massive legacy enterprise ERP system, generating comprehensive, bottom-up architectural and functional documentation in three weeks.

---

## The Challenge

The target system represented a classic enterprise monolithic codebase:
- **Age**: 20+ years of continuous active development.
- **Scale**: Over 3 million lines of Object Pascal / Delphi and SQL Server stored procedures.
- **Complexity**: Hundreds of interconnected database tables, thousands of visual form files (`.dfm`), and tens of thousands of business routines.
- **Documentation State**: Sparse, outdated, and largely tribal knowledge retained by a few senior engineers.
- **Business Impact**: High support ticket resolution times, risk of catastrophic regressions during feature updates, and slow engineering onboarding.

---

## The Strategy: Bottom-Up Recursive Synthesis

Attempting to feed thousands of legacy files into a large language model all at once is impossible due to context limits, attention degradation, and extreme financial cost.

Instead, the team deployed a **Bottom-Up Recursive Synthesis** pipeline:

```
[Layer 1: Leaf Symbols]
Extract and document individual routines, methods, and private helpers.
                          |
                          v
[Layer 2: Classes & Modules]
Synthesize module docstrings by aggregating documented member methods.
                          |
                          v
[Layer 3: UI & Form Bindings]
Parse DFM visual trees to link buttons, grids, and dataset events to business logic.
                          |
                          v
[Layer 4: Community Architectural Synthesis]
Apply Louvain community detection on the call graph to generate subsystem guides.
```

---

## Execution: The 3-Week Timeline

### Week 1: AST Parsing, Graph Construction and Indexing
- Ingested all source units and form files through the custom AST parser.
- Extracted 45,000+ distinct symbols (classes, interfaces, methods, form components).
- Constructed the multi-relational `CodeGraph`, linking 120,000+ directed relationship edges (`calls`, `inherits`, `binds_ui`).
- Applied Louvain modularity clustering, automatically identifying 28 cohesive functional business subsystems (e.g. Accounts Receivable, Billing, Equipment Logistics, Contract Lifecycle).

### Week 2: Bottom-Up AI Documentation Generation
- Deployed parallel execution workers running structured prompt pipelines.
- Routines were documented with input constraints, business exception conditions, and database table access patterns.
- Form components were mapped to their underlying event handlers, explaining what each user screen button and data grid actually triggered.
- Tracing with circuit breakers ensured continuous execution with zero telemetry bottlenecks.

### Week 3: Architectural Review, Verification and Search Deployment
- The generated documentation was indexed into a hybrid search store (SQLite FTS5 + dense vector embeddings).
- Interactive GraphRAG queries allowed developers to ask: *"What happens when a contract is renewed?"* and receive a multi-hop trace across forms, services, and database queries.
- Senior domain experts validated accuracy across critical financial and billing units.

---

## Results and Business Outcomes

| Metric | Before Intervention | After Documentation Deployment | Impact |
|---|---|---|---|
| **Codebase Documentation Coverage** | < 8% of routines | **96% of units, classes, and screens** | 12x increase in documented assets |
| **New Developer Onboarding Time** | 6 to 9 months | **4 to 6 weeks** | 75% reduction in time to first production commit |
| **Support Root-Cause Diagnostics** | 4 to 8 hours per complex ticket | **30 to 45 minutes** | Rapid symbol lookup and blast radius tracing |
| **Regression Risk on Refactoring** | High (frequent unintended side-effects) | Low (impact analysis runs before every PR) | Eliminated unexpected cross-module breakages |

---

## Lessons Learned

1. **Exact Lexical Search Is Essential**: In large legacy systems, developers search for exact table names, error numbers, and method identifiers. Pure vector search failed on exact acronyms; hybrid RRF was mandatory.
2. **UI Form Bindings Bridge the Gap**: In desktop architectures, business logic is frequently bound directly into visual form event handlers. Parsing form definitions (`.dfm`) and creating explicit `binds_ui` graph edges was critical for explaining user workflows.
3. **Structured Verification Prevents Hallucinations**: Grounding every docstring generation step with exact AST signatures and call graph edges prevented the LLM from inventing non-existent database tables or methods.
