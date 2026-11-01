# Pipelines: LangGraph Workflow Orchestration

Complex software automation requires workflows that go beyond single-turn prompt interactions. It demands structured state machines, branching logic, validation loops, and human-in-the-loop authorization gates.

`faccoder-agents` features a modular pipeline execution engine built on top of **LangGraph**, providing reusable execution blocks, dry-run simulations, and error boundaries.

---

## Pipeline Architecture

A `faccoder` pipeline is a directed graph where state flows through typed execution blocks:

```
[Initial State]
       |
       v
+------------------------+
|    ValidatorBlock      | -> Ensures required keys exist in state
+-----------+------------+
            |
            v
+------------------------+
|      PromptBlock       | -> Formats prompt & executes model tier via core registry
+-----------+------------+
            |
            v
+------------------------+
|     ConditionBlock     | -> Routes to next block based on state inspection
+-----+------------+-----+
      |            |
 [Passes]       [Fails]
      |            |
      v            v
+-----------+ +----------+
| Approval  | | Correct  |
|  Block    | |  Block   |
+-----------+ +----------+
```

---

## Reusable Building Blocks

`faccoder-agents` ships with four standardized blocks:

### 1. `ValidatorBlock`
Verifies that required keys are present and conform to type constraints before proceeding to costly model calls:

```python
from faccoder_agents.engine.blocks import ValidatorBlock

validator = ValidatorBlock(
    name="validate-input",
    required_keys=["code_snippet", "language"],
)
```

### 2. `PromptBlock`
Interpolates state variables into prompt templates and invokes the model registry:

```python
from faccoder_agents.engine.blocks import PromptBlock

prompt_block = PromptBlock(
    name="generate-unit-tests",
    prompt_template="Write pytest unit tests covering edge cases for the following {language} code:\n\n{code_snippet}",
    output_key="generated_tests",
    tier="medium",
)
```

### 3. `ConditionBlock`
Enables dynamic routing based on Boolean conditions or predicate functions:

```python
from faccoder_agents.engine.blocks import ConditionBlock


def tests_passed(state: dict) -> bool:
    return state.get("test_exit_code") == 0


router = ConditionBlock(
    name="check-test-result",
    condition=tests_passed,
    on_true="generate-pull-request",
    on_false="diagnose-and-fix",
)
```

### 4. `HumanApprovalBlock`
Suspends execution when an action requires human sign-off (e.g. database schema migrations or Git pushes):

```python
from faccoder_agents.engine.blocks import HumanApprovalBlock

approval = HumanApprovalBlock(
    name="approve-git-push",
    action_description="Push layer branch to remote origin",
    timeout_minutes=15,
    require_dry_run=True,
)
```

---

## Constructing and Executing a Pipeline

Constructing a complete pipeline with `PipelineBuilder`:

```python
from faccoder_agents.engine import PipelineBuilder
from faccoder_agents.engine.blocks import (
    ConditionBlock,
    HumanApprovalBlock,
    PromptBlock,
    ValidatorBlock,
)

builder = PipelineBuilder("feature-generation")

# 1. Validate inputs
builder.add_block(ValidatorBlock(name="validate-spec", required_keys=["feature_spec"]))

# 2. Generate implementation code
builder.add_block(
    PromptBlock(
        name="implement-feature",
        prompt_template="Implement the following feature in Python:\n\n{feature_spec}",
        output_key="code_diff",
        tier="medium",
    )
)

# 3. Gate PR creation behind human approval
builder.add_block(
    HumanApprovalBlock(
        name="approve-pr",
        action_description="Create pull request for generated feature",
        require_dry_run=True,
    )
)

# Compile into executable LangGraph app
pipeline = builder.build()

# Execute pipeline
initial_state = {"feature_spec": "Add JWT token refresh endpoint"}
final_state = pipeline.invoke(initial_state)
print("Pipeline Result:", final_state["status"])
```

---

## Dry-Run and Execution Safeguards

To prevent cascading errors or runaway costs in autonomous pipelines, `faccoder` enforces strict guardrails:

1. **Max Recursion Depth**: Pipelines terminate automatically if state cycles exceed configurable depth limits (default: 10 steps).
2. **Tool Execution Caps**: Limits the total number of tool invocations allowed within a single pipeline run.
3. **Dry-Run Enforcement**: Destructive blocks execute in `--dry-run` simulation mode until explicitly authorized by a valid approval token.
