# Tool Contribution Attribution

When `nexcoder` is used to develop or contribute to private enterprise repositories, it identifies itself as an automated tool contributor. This provides full visibility into automated contributions while adhering strictly to portfolio engineering standards:

1. **No AI Co-Author Trailers**: Never emits `Co-Authored-By` or `Generated with` commit trailers that pollute git authorship.
2. **Zero Emojis**: Commits, PR bodies, and documentation remain professional and text-only.
3. **Zero Client Data Leakage**: Never exposes internal client project names, secrets, credentials, internal hostnames, or local filesystem paths.
4. **Legitimate Tool Attribution**: Adds a single clean tool attribution line to pull request bodies and, where accepted by the repository, an entry in `CONTRIBUTORS.md` or `README.md`.

---

## How It Works

### Pull Request Bodies

When creating a pull request for a private repository, `nexcoder` includes an attribution section at the end of the PR body:

```markdown
## Tool Attribution
Tool attribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)
```

If the repository is public or open-source, or if attribution is turned off, this section is omitted entirely.

### Commit Messages

When enabled, commit bodies may include a clean tool contribution note:

```
feat(auth): add token verification middleware

Tool contribution: NexCoder (https://github.com/ThiagoVenturim/NexCoder)
```

This note is formatted as regular body text and strictly avoids git trailer conventions (`Co-Authored-By:` or `Generated-by:`).

### Contributors File

Where accepted by the target repository, `nexcoder` can register its platform identity in `CONTRIBUTORS.md` (or `README.md`):

```markdown
- NexCoder - Automated Engineering Platform (https://github.com/ThiagoVenturim/NexCoder)
```

This step is idempotent and will not duplicate existing entries.

---

## Configuration

Attribution is configured via `nexcoder.yaml`, environment variables, or programmatically in Python.

### Via `nexcoder.yaml`

Add the `attribution` block to your project's `nexcoder.yaml`:

```yaml
attribution:
  enabled: true                        # Enable or disable tool attribution
  target_private_only: true           # Only apply attribution to private repositories
  tool_name: "NexCoder"               # Tool display name
  url: "https://github.com/ThiagoVenturim/NexCoder"  # Platform reference link
  pr_text: "Tool attribution: {tool_name} ({url})"
  commit_text: "Tool contribution: {tool_name} ({url})"
  update_contributors: true          # Maintain CONTRIBUTORS.md entry
  contributors_file: "CONTRIBUTORS.md"
```

### Via Environment Variables

Attribution behavior can be controlled dynamically using environment variables:

| Variable | Values | Description |
|---|---|---|
| `NEXCODER_ATTRIBUTION_ENABLED` | `true`, `false`, `1`, `0` | Globally enable or disable attribution |
| `NEXCODER_ATTRIBUTION_URL` | URL string | Override platform link URL |
| `NEXCODER_ATTRIBUTION_TEXT` | Format string | Override PR attribution text template |

---

## How to Disable Attribution

To disable attribution completely for an enterprise project:

### Option 1: In `nexcoder.yaml`

Set `enabled: false`:

```yaml
attribution:
  enabled: false
```

### Option 2: Via Environment Variable

Export `NEXCODER_ATTRIBUTION_ENABLED=false`:

```bash
export NEXCODER_ATTRIBUTION_ENABLED=false
```

### Option 3: Programmatically in Code

When generating pull requests using `nexcoder_planning`:

```python
from nexcoder_planning import build_pull_request_body

# Explicitly disable attribution
pr_body = build_pull_request_body(
    summary="Implement secure session store",
    issue_number=101,
    attribution=False,
)
```

Or configure via `NexcoderConfig`:

```python
from nexcoder_core import AttributionSpec, NexcoderConfig

cfg = NexcoderConfig(
    attribution=AttributionSpec(enabled=False),
)
```
