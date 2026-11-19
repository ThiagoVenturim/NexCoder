# Assisted prospecting and proposals (lead-gen)

`nexcoder_agents.leadgen` helps find businesses in a region that have no site, or a weak
one, and prepares a proposal for a human to decide whether to send. It is built around
guardrails for ethics and law: public data only, passive observation only, and human
approval for every e-mail.

## Flow

1. **Search** (`LeadGenAssistant.find_candidates(region, segment)`): queries the
   configured business sources and ranks candidates by how much their web presence could
   improve.
2. **Passive look** (`PassiveSiteInspector`): for each listed site, reads `robots.txt`
   and the published home page with one plain GET each. Signals: no website, no HTTPS,
   site offline, outdated design, not responsive, no contact information.
3. **Proposal** (`LeadGenAssistant.build_proposal(candidate)`): diagnosis, suggestions,
   a responsive HTML mockup and a cost estimate from the product cost calculator
   (`nexcoder_planning.cost.ProductCostCalculator`).
4. **Draft** (`LeadGenAssistant.prepare_draft(proposal)`): an e-mail draft with the report
   and the mockup attached. Preparing a draft never sends anything.
5. **Review and send** (`OutreachSender`): the draft goes to a named human reviewer, who
   receives the preview and a single-use approval code from the nexcoder-control
   `ApprovalTokenManager`. Only `send_approved(draft, approval_code, approved_by)` sends,
   one message at a time, through the existing `EmailService`.

## What it may do

- Use sources that declare `kind` as `official_api`, `open_data` or `licensed_directory`,
  declare that their terms allow automated access and reference those terms
  (`ensure_legitimate_source`). Implement the `BusinessSource` protocol to add, for
  example, an official places API client, following its terms of use.
- Read the public home page as a visitor would, after checking `robots.txt`
  (RFC 9309: a 4xx answer allows, a 5xx answer disallows). Requests to the same host are
  spaced by `min_interval_seconds`.

## What it refuses (covered by tests in `packages/agents/tests/test_leadgen.py`)

- **No active scanning.** The inspector can only request the home page and
  `robots.txt`; query parameters are dropped; there are no other paths, ports, payloads,
  scanners, sockets or subprocesses. "Weak security" in a proposal means only what a
  visitor sees, such as a missing HTTPS. A real security assessment needs the target to
  pass `TargetAuthorizationGate` (see `require_authorized_security_target` and
  [USAGE_POLICY.md](../USAGE_POLICY.md)) and then runs in nexcoder-security, never here.
- **No automatic or bulk e-mail.** There is no bulk path (`send_bulk` always raises).
  A send needs a prior review request, the approval code and the approver name. A draft
  changed after review must be reviewed again. `OutreachSender` refuses an `EmailService`
  configured with `require_human_approval=False`.
- **Anti-spam, LGPD and CAN-SPAM.** `OutreachPolicy` requires sender name, organization,
  e-mail and postal address, a legal basis (default: legitimate interest, LGPD art. 7,
  IX) and an `https://` or `mailto:` unsubscribe address. Every draft states that it is a
  commercial message, carries the unsubscribe link and a `List-Unsubscribe` header.
  `validate_subject` refuses fake replies or forwards, billing wording, false urgency,
  prizes, capitals and repeated exclamation marks.
- **Rate limit and do-not-contact list.** `DailySendLimiter` caps sends per rolling 24
  hours (default 20) on top of the EmailService provider limits. `DoNotContactList`
  blocks addresses and whole domains, is checked when searching, drafting, reviewing and
  sending, and stores only SHA-256 hashes. `record_opt_out` handles unsubscribe requests.
- **Data minimization.** Only business fields are kept (`name`, `segment`, `region`,
  `website`, `public_email`, `public_phone`, `address`); any other column, such as owner
  or partner names, is dropped, and values that look like individual tax ids are
  discarded. Sources named like scraped or purchased lists are refused. Do not commit
  prospect data to the repository.

## Example

```python
from nexcoder_agents.leadgen import (
    CsvOpenDataSource, LeadGenAssistant, OutreachPolicy, OutreachSender,
)
from nexcoder_control.email.service import EmailService

policy = OutreachPolicy(
    sender_name="Your Name",
    sender_organization="Your Studio",
    sender_email="sales@your-domain.example",
    postal_address="Street, number, city",
    unsubscribe_url="https://your-domain.example/unsubscribe?c={code}",
)
source = CsvOpenDataSource("data/businesses.csv", terms_reference="Open data license of the portal")
assistant = LeadGenAssistant([source], policy)

candidates = assistant.find_candidates("Vitoria", "padaria")
proposal = assistant.build_proposal(candidates[0])
draft = assistant.prepare_draft(proposal)          # nothing is sent

sender = OutreachSender(EmailService(), policy)
review = sender.submit_for_review(draft, reviewer="Your Name")
# The reviewer reads review.preview and, if they agree, replies with the approval code.
sender.send_approved(draft, approval_code=review.approval_code, approved_by="Your Name")
```

The operator is responsible for confirming that each source allows this use and that
the legal basis applies to each contact.
