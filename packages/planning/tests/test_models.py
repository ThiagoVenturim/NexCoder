from faccoder_planning.models import AcceptanceCriterion, Epic, Plan, Story, Task


def test_acceptance_criterion_gherkin():
    crit = AcceptanceCriterion(
        given="a user is on the login page",
        when="they enter valid credentials",
        then="they are redirected to dashboard",
    )
    rendered = crit.to_gherkin()
    assert "Given a user is on the login page" in rendered
    assert "When they enter valid credentials" in rendered
    assert "Then they are redirected to dashboard" in rendered


def test_task_marker_and_markdown():
    crit = AcceptanceCriterion(
        given="an unauthenticated user",
        when="accessing /protected",
        then="HTTP 401 Unauthorized is returned",
    )
    task = Task(
        id="TSK-01-01",
        title="Implement Auth Middleware",
        description="Check Bearer token in request header",
        acceptance_criteria=[crit],
        estimate_hours=6.0,
        layer="backend",
        dependencies=["TSK-01-00"],
        recommended_agent="backend-engineer",
    )

    body = task.format_markdown_body()
    assert task.build_marker() in body
    assert f"<!-- faccoder-id: {task.faccoder_id} -->" in body
    assert "TSK-01-01" in body
    assert "backend-engineer" in body
    assert "HTTP 401 Unauthorized" in body


def test_plan_dependencies_and_topological_sort():
    t1 = Task(id="T1", title="Database Schema", estimate_hours=4.0)
    t2 = Task(id="T2", title="Repositories", estimate_hours=4.0, dependencies=["T1"])
    t3 = Task(id="T3", title="API Endpoints", estimate_hours=8.0, dependencies=["T2"])
    t4 = Task(id="T4", title="Frontend UI", estimate_hours=6.0, dependencies=["T3"])

    epic = Epic(
        id="EP-01",
        title="Core Platform",
        stories=[Story(id="US-01", title="Foundation", tasks=[t4, t2, t1, t3])],
    )
    plan = Plan(title="Project Plan", epics=[epic])

    # No errors
    errors = plan.validate_dependencies()
    assert not errors

    # Topological sort
    sorted_tasks = plan.topological_sort_tasks()
    sorted_ids = [t.id for t in sorted_tasks]
    assert sorted_ids.index("T1") < sorted_ids.index("T2")
    assert sorted_ids.index("T2") < sorted_ids.index("T3")
    assert sorted_ids.index("T3") < sorted_ids.index("T4")


def test_plan_missing_dependency():
    t1 = Task(id="T1", title="Task 1", dependencies=["NON_EXISTENT"])
    plan = Plan(
        title="Plan",
        epics=[Epic(id="EP-1", title="Epic", stories=[Story(id="US-1", title="Story", tasks=[t1])])],
    )
    errors = plan.validate_dependencies()
    assert any("non-existent" in err for err in errors)


def test_plan_cyclic_dependency():
    t1 = Task(id="T1", title="Task 1", dependencies=["T2"])
    t2 = Task(id="T2", title="Task 2", dependencies=["T1"])
    plan = Plan(
        title="Plan",
        epics=[Epic(id="EP-1", title="Epic", stories=[Story(id="US-1", title="Story", tasks=[t1, t2])])],
    )
    errors = plan.validate_dependencies()
    assert any("Cyclic dependency detected" in err for err in errors)
