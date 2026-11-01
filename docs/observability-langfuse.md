# Observability with Langfuse

Complex multi-agent pipelines require deep observability: tracking latency across reasoning loops, monitoring token consumption, auditing tool inputs/outputs, and enforcing cost controls.

`faccoder` integrates natively with **Langfuse** (self-hosted or cloud) while incorporating an automatic **circuit breaker** to ensure telemetry failures never disrupt production tasks.

---

## Why Langfuse?

1. **Full Trace Graphs**: Visualizes the nested hierarchy of pipeline steps: `Intake -> ResearchSquad -> JuryDebate -> TaskDecomposition -> CodeGen`.
2. **Cost and Token Tracking**: Attributes model costs (USD) per user, project, persona, and pipeline execution.
3. **Evaluation Datasets and Scores**: Captures human approval feedback, jury scores, and automated test pass/fail metrics directly into trace spans.
4. **Self-Hostable**: Can be deployed on-premises using Docker Compose with PostgreSQL and ClickHouse for complete data sovereignty.

---

## The Circuit Breaker Pattern

In distributed agent workflows, an external telemetry service can become a single point of failure if network timeouts occur.

`faccoder-core` wraps the Langfuse handler in `SafeLangfuseCallbackHandler` with an integrated circuit breaker:

```
[Agent Invocation]
        |
        v
[Langfuse Safe Wrapper]
        |
   +----+----+
   | Circuit |
   | State?  |
   +----+----+
        |
        +-- CLOSED: Normal operation --> Send telemetry to Langfuse
        |                                (Record success; reset fail counter)
        |
        +-- OPEN: Consecutive errors > Threshold --> Bypass network completely
                                                     (Log warning once; return instantly)
        |
        +-- HALF-OPEN: Cooldown expired --> Probe with single test trace
```

### Circuit Breaker Behavior
- If Langfuse is unreachable, consecutive connection timeouts increment an internal failure counter.
- When the threshold is reached (default: 3 failures), the circuit trips to **OPEN**.
- While OPEN, all telemetry calls return immediately as zero-latency no-ops. Pipeline execution continues uninterrupted.
- After a configurable cooldown window (default: 60 seconds), the circuit enters **HALF-OPEN** to test service recovery.

---

## Configuration

Set the standard Langfuse environment variables:

```bash
# Langfuse Credentials
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_HOST="https://cloud.langfuse.com" # or "http://localhost:3000"

# Optional Circuit Breaker Tuning
export FACCODER_LANGFUSE_TIMEOUT_MS="2000"
export FACCODER_LANGFUSE_MAX_FAILURES="3"
export FACCODER_LANGFUSE_COOLDOWN_SEC="60"
```

If `LANGFUSE_PUBLIC_KEY` is omitted, `faccoder` automatically disables telemetry without throwing errors.

---

## Tracing in Code

### Automatic Pipeline Tracing

When invoking models or executing pipelines via `faccoder`, tracing is attached automatically through `default_callbacks`:

```python
from faccoder_core import get_chat_model, load_config

config = load_config()

# Models obtained through get_chat_model automatically attach default_callbacks:
# - Langfuse safe tracing (with automatic circuit breaker)
# - UsageCallback for per-run token and cost metering
model = get_chat_model("medium", config=config)
response = model.invoke("Draft a unit test plan for the authentication module.")
```

### Attaching Callbacks to Custom Pipelines

For explicit callback injection into custom LangGraph pipelines:

```python
from faccoder_core import load_config
from faccoder_core.observability.callbacks import default_callbacks

config = load_config()
callbacks = default_callbacks(config, tier="medium", model="claude-3-5-sonnet")

# Pass callbacks to LangGraph invoke config
state = pipeline.invoke({"prd": prd_text}, config={"callbacks": callbacks})
```

---

## Self-Hosting Langfuse via Docker Compose

To run a self-hosted Langfuse instance locally or within your private VPC:

```yaml
version: "3.8"

services:
  langfuse-server:
    image: ghcr.io/langfuse/langfuse:latest
    depends_on:
      - db
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@db:5432/langfuse
      - NEXTAUTH_SECRET=my-super-secret-key-must-be-32-chars
      - SALT=my-salt-phrase-min-32-chars-long
      - NEXTAUTH_URL=http://localhost:3000
      - TELEMETRY_ENABLED=false

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse
      - POSTGRES_DB=langfuse
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Launch the stack:

```bash
docker compose -f docker-compose.langfuse.yml up -d
```

Navigate to `http://localhost:3000`, create your project, and generate API keys for `faccoder`.
