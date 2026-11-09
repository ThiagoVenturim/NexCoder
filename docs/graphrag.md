# GraphRAG: Code Graphs and Community Detection

Standard RAG answers local, pinpoint questions well (e.g. *"Where is the calculate_discount function defined?"*). However, it struggles with holistic, architectural questions:
- *"How is the billing subsystem structured?"*
- *"What is the blast radius if I change the PaymentGateway interface?"*
- *"Are there circular dependencies between the order and inventory modules?"*

To answer these questions, `nexcoder-code-intel` implements **GraphRAG**: constructing a multi-relational code knowledge graph and applying hierarchical community detection.

---

## 1. The CodeGraph Architecture

The `CodeGraph` models source code as a directed multigraph where nodes represent syntactic symbols and edges represent structural relationships:

```
[UserService] --(calls)--> [PasswordHasher]
      |
 (inherits)
      v
[BaseService] --(implements)--> [IService]
      ^
      |
 (binds_ui)
      |
[UserForm (DFM)]
```

### Supported Edge Types
- `calls`: Function invocation or method dispatch.
- `inherits`: Class inheritance or subclass relationship.
- `implements`: Interface fulfillment.
- `imports`: Module or package dependency.
- `references`: Field, constant, or variable access.
- `binds_ui`: Association between a visual UI component (e.g. Delphi DFM form button) and backend event handler code.

---

## 2. Transitive Blast Radius and Impact Analysis

Before proposing a refactoring or modifying a public signature, agents query the code graph for transitive impact:

```python
from nexcoder_code_intel import CodeGraph

graph = CodeGraph()
# ... symbols added ...

# Analyze impact with breadth-first traversal
report = graph.impact_analysis("PaymentGateway", max_depth=3)

print("Direct Dependents:", len(report.direct_dependents))
print("Transitive Dependents:", len(report.transitive_dependents))
print("Blast Radius Score:", report.risk_score)
```

The report identifies:
1. **Direct Callers**: Methods directly invoking the symbol.
2. **Transitive Cascades**: Downstream services impacted through multiple hops.
3. **Risk Score**: Normalized metric factoring in coupling, fan-in, and depth.

---

## 3. Louvain Community Detection for System Summaries

Answering high-level architectural questions requires abstracting thousands of individual functions into cohesive functional domains.

`nexcoder-code-intel` runs the **Louvain Modularity Algorithm** over the code graph:

```
+-------------------------------------------------------------+
| System Architecture Graph                                   |
|                                                             |
|  +---------------------------+  +-------------------------+ |
|  | Community 1: Auth Module  |  | Community 2: Billing    | |
|  | - UserEntity              |  | - InvoiceManager        | |
|  | - TokenVerifier           |  | - GatewayAdapter        | |
|  | - SessionStore            |  | - TaxCalculator         | |
|  +-------------+-------------+  +------------+------------+ |
|                |                             |              |
|                +------------(calls)----------+              |
+-------------------------------------------------------------+
```

### Hierarchical Architectural Summaries
1. **Node Clustering**: Closely-coupled classes and functions are grouped into communities.
2. **Bottom-Up Synthesis**: An LLM generates a dense architectural summary for each community based on its public interfaces and internal calls.
3. **Multi-Hop Query Resolution**: High-level questions match community summaries first, immediately pruning irrelevant modules and routing queries to the exact subgraphs needed.

---

## GraphRAG vs Standard RAG Comparison

| Capability | Standard Vector RAG | CodeGraph + GraphRAG |
|---|---|---|
| **Lookup Exact Function** | Good (with lexical FTS) | Excellent |
| **Understand Call Hierarchies** | Poor (blind to relationships) | Native (directed graph traversal) |
| **Identify Blast Radius** | Cannot determine | Deterministic BFS impact report |
| **Architectural Overview** | Suffers from context truncation | Cohesive via Louvain community summaries |
| **UI-to-Backend Binding** | Poor | Explicit `binds_ui` relationship edges |
