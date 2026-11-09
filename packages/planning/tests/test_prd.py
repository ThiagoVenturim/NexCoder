import json

from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_planning import PRDConverter

SAMPLE_PRD = """# PRD: Tenant Authentication System

# Epic: User Access Management
## Story: JWT Authentication Flow
### Task: Implement Token Generation
- Layer: backend
- Estimate: 4.5h
- Agent: backend-engineer
- Given a valid tenant user credentials
- When the login endpoint is requested
- Then return a valid JWT token signed with HMAC-SHA256

### Task: Implement Token Validation Middleware
- Layer: backend
- Estimate: 6h
- Agent: backend-engineer
- Depends on: TSK-01
- Given an incoming request with Authorization header
- When the token is verified
- Then attach the user claims to request state

## Story: Password Reset
### Task: Send Password Reset Email
- Layer: backend
- Estimate: 3h
- Agent: backend-engineer
- Depends on: TSK-02
- Given a registered email address
- When requested via reset API
- Then dispatch an email with one-time token
"""


def test_prd_converter_deterministic_parsing():
    converter = PRDConverter()
    plan = converter.parse_markdown(SAMPLE_PRD)

    assert plan.title == "Tenant Authentication System"
    assert len(plan.epics) == 1
    epic = plan.epics[0]
    assert epic.title == "User Access Management"
    assert len(epic.stories) == 2

    # Verify Story 1 & tasks
    s1 = epic.stories[0]
    assert s1.title == "JWT Authentication Flow"
    assert len(s1.tasks) == 2

    t1 = s1.tasks[0]
    assert t1.title == "Implement Token Generation"
    assert t1.layer == "backend"
    assert t1.estimate_hours == 4.5
    assert t1.recommended_agent == "backend-engineer"
    assert len(t1.acceptance_criteria) == 1
    assert "valid tenant user credentials" in t1.acceptance_criteria[0].given
    assert "login endpoint is requested" in t1.acceptance_criteria[0].when
    assert "return a valid JWT token" in t1.acceptance_criteria[0].then

    t2 = s1.tasks[1]
    assert t2.dependencies == ["TSK-01"]
    assert t2.estimate_hours == 6.0

    # Verify Story 2
    s2 = epic.stories[1]
    assert s2.title == "Password Reset"
    assert len(s2.tasks) == 1
    t3 = s2.tasks[0]
    assert t3.dependencies == ["TSK-02"]

    # Total hours
    assert plan.total_hours() == 13.5


def test_prd_converter_llm_mode():
    converter = PRDConverter()
    fake_plan = {
        "title": "Cloud Backup Feature",
        "description": "Automated snapshotting",
        "epics": [
            {
                "id": "EP-01",
                "title": "Backup Automation",
                "stories": [
                    {
                        "id": "US-01",
                        "title": "Daily Snapshots",
                        "tasks": [
                            {
                                "id": "TSK-01",
                                "title": "Create S3 Bucket Sync",
                                "description": "Trigger daily snapshot",
                                "estimate_hours": 8.0,
                                "layer": "devops",
                                "recommended_agent": "devops-engineer",
                                "acceptance_criteria": [
                                    {
                                        "given": "A scheduled cron trigger",
                                        "when": "The worker activates",
                                        "then": "Write snapshot to S3 bucket",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    fake_llm = FakeChatModel(responses=[json.dumps(fake_plan)])
    plan = converter.convert("Backup PRD text", use_llm=True, llm=fake_llm)

    assert plan.title == "Cloud Backup Feature"
    assert len(plan.all_tasks()) == 1
    task = plan.all_tasks()[0]
    assert task.layer == "devops"
    assert task.estimate_hours == 8.0
    assert task.recommended_agent == "devops-engineer"
