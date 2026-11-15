# Email Dispatch and Governance

NexCoder integrates automated report and proposal delivery with Google Gmail (REST API / OAuth2), Microsoft Outlook / Microsoft 365 (Microsoft Graph API / OAuth2), and generic SMTP fallback.

Every email is dispatched from the user account under strict governance controls:
1. **Mandatory Human Approval**: No automated bulk mailing. Every outgoing dispatch requires explicit human confirmation or a single-use timing-safe approval token.
2. **Cryptographic Audit Ledger**: All attempts, approvals, dispatches, and failures are appended to the tamper-evident SHA-256 chained audit log in the control plane.
3. **Platform Rate Limiting**: Built-in sliding-window rate limiters prevent API throttling or quota bans from Google, Microsoft, and SMTP relays.
4. **Attachments & Rich HTML**: Full support for PDFs, reports, charts, screenshots, and MIME multipart alternatives.
5. **Reusable Templates**: Pre-configured templates for productivity reports, architectural proposals, security reviews, and custom alerts.
6. **Graceful Degradation**: Without credentials configured, email functionality safely turns off without breaking downstream pipelines.

---

## Configuration

Credentials must be stored exclusively in `.env` or environment variables; never commit credentials to repositories.

### 1. Gmail (Google OAuth2 API)

```bash
# Provider selection (auto, gmail, outlook, smtp, none)
NEXCODER_EMAIL_PROVIDER=gmail

# Google Cloud OAuth 2.0 Client credentials
NEXCODER_GMAIL_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
NEXCODER_GMAIL_CLIENT_SECRET=your-google-client-secret
NEXCODER_GMAIL_REFRESH_TOKEN=your-google-refresh-token
NEXCODER_GMAIL_USER_EMAIL=engineer@example.com
```

### 2. Outlook / Microsoft 365 (Microsoft Graph API)

```bash
NEXCODER_EMAIL_PROVIDER=outlook

# Microsoft Entra ID (Azure AD) App registration credentials
NEXCODER_OUTLOOK_CLIENT_ID=your-azure-app-client-id
NEXCODER_OUTLOOK_CLIENT_SECRET=your-azure-app-client-secret
NEXCODER_OUTLOOK_REFRESH_TOKEN=your-azure-refresh-token
NEXCODER_OUTLOOK_TENANT_ID=common
NEXCODER_OUTLOOK_USER_EMAIL=engineer@example.com
```

### 3. Fallback SMTP

```bash
NEXCODER_EMAIL_PROVIDER=smtp
NEXCODER_SMTP_HOST=smtp.mailgun.org
NEXCODER_SMTP_PORT=587
NEXCODER_SMTP_USERNAME=postmaster@example.com
NEXCODER_SMTP_PASSWORD=your-smtp-password
NEXCODER_SMTP_USE_TLS=true
NEXCODER_SMTP_FROM_EMAIL=reports@example.com
```

### 4. Governance & Policies

```bash
# Require human confirmation before sending (default: true)
NEXCODER_EMAIL_REQUIRE_APPROVAL=true

# Anti-bulk limit: maximum recipients per single send (default: 10)
NEXCODER_EMAIL_MAX_RECIPIENTS=10

# Platform rate limits in requests per minute (RPM)
NEXCODER_EMAIL_RATE_LIMIT_GMAIL_RPM=60
NEXCODER_EMAIL_RATE_LIMIT_OUTLOOK_RPM=30
NEXCODER_EMAIL_RATE_LIMIT_SMTP_RPM=30
```

---

## Programmatic Usage

### Sending an Email with Attachment and Confirmation

```python
from nexcoder_control.email import (
    EmailAttachment,
    EmailMessage,
    EmailService,
)

service = EmailService()

attachment = EmailAttachment(
    filename="sprint_report.pdf",
    file_path="artifacts/sprint_report.pdf",
    content_type="application/pdf",
)

message = EmailMessage(
    subject="NexCoder Sprint 1 Summary",
    recipients=["lead@example.com"],
    body_html="<h2>Sprint 1 Summary</h2><p>Report attached.</p>",
    body_text="Sprint 1 Summary: report attached.",
    attachments=[attachment],
)

# Explicit human confirmation
result = service.send_email(message, confirmed=True)
print(f"Dispatched via {result.provider}, ID: {result.message_id}")
```

### Human Approval Workflow (Fail-Closed)

```python
from nexcoder_control.email import (
    EmailApprovalRequiredError,
    EmailMessage,
    EmailService,
)

service = EmailService()
message = EmailMessage(
    subject="Enterprise Pricing Proposal",
    recipients=["procurement@enterprise.com"],
    template_name="proposal_submission",
    template_vars={
        "proposal_title": "Architecture Modernization Proposal",
        "verdict": "APPROVED",
        "score": "9.0/10",
        "author": "Architecture Committee",
        "executive_summary": "Approved for phased migration.",
        "recipient_name": "Procurement Lead",
        "sender_name": "Lead Architect",
    },
)

# 1. Dispatching without token raises EmailApprovalRequiredError
try:
    service.send_email(message, confirmed=False)
except EmailApprovalRequiredError as exc:
    print(f"Approval Required! Token ID: {exc.token_id}")
    print(f"Preview: {exc.preview}")

# 2. Or request pre-flight token explicitly
token_id, raw_secret, preview = service.request_approval(message, approver="lead_engineer")

# 3. Present preview to human in CLI or Web UI, then consume single-use secret
result = service.send_email(message, approval_token=raw_secret)
print(f"Sent with approval! Audit Event ID: {result.audit_event_id}")
```

---

## CLI Usage

### View Email Status

```bash
nexcoder-control email status
```

### List Reusable Templates

```bash
nexcoder-control email templates
```

### Send Email via CLI

```bash
nexcoder-control email send \
  --to "stakeholder@example.com" \
  --subject "Engineering Report" \
  --body "Please find the report attached." \
  --attachment "report.pdf" \
  --confirm
```

### Run Connectivity Test

```bash
nexcoder-control email test --to "me@example.com" --provider gmail
```
