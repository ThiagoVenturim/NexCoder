"""Domain models for agentic backlog planning: epics, stories, tasks, and criteria."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

MARKER_TEMPLATE = "<!-- nexcoder-id: {nexcoder_id} -->"


class AcceptanceCriterion(BaseModel):
    """Given/When/Then acceptance criteria for a task or story."""

    given: str
    when: str
    then: str

    def to_gherkin(self) -> str:
        """Format criterion in standard Gherkin syntax."""
        return f"Given {self.given}\nWhen {self.when}\nThen {self.then}"


class Task(BaseModel):
    """Granular actionable task derived from a user story."""

    id: str
    nexcoder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    estimate_hours: float = 0.0
    story_points: int | None = None
    layer: str = "general"
    dependencies: list[str] = Field(default_factory=list)
    recommended_agent: str | None = None
    labels: list[str] = Field(default_factory=list)
    status: str = "backlog"

    def build_marker(self) -> str:
        """Generate the hidden HTML tracking comment embedded in ticket bodies."""
        return MARKER_TEMPLATE.format(nexcoder_id=self.nexcoder_id)

    def format_markdown_body(self) -> str:
        """Render a full markdown description including acceptance criteria and tracking marker."""
        sections = []

        if self.description.strip():
            sections.append(self.description.strip())

        metadata = [
            f"- **Task ID**: {self.id}",
            f"- **Layer**: {self.layer}",
            f"- **Estimate**: {self.estimate_hours}h",
        ]
        if self.recommended_agent:
            metadata.append(f"- **Recommended Agent**: {self.recommended_agent}")
        if self.dependencies:
            metadata.append(f"- **Dependencies**: {', '.join(self.dependencies)}")

        sections.append("### Metadata\n" + "\n".join(metadata))

        if self.acceptance_criteria:
            criteria_lines = ["### Acceptance Criteria"]
            for idx, criterion in enumerate(self.acceptance_criteria, start=1):
                criteria_lines.append(f"#### Scenario {idx}")
                criteria_lines.append(f"- **Given**: {criterion.given}")
                criteria_lines.append(f"- **When**: {criterion.when}")
                criteria_lines.append(f"- **Then**: {criterion.then}")
            sections.append("\n".join(criteria_lines))

        sections.append(self.build_marker())
        return "\n\n".join(sections)


class Story(BaseModel):
    """User story grouping related tasks into a deliverable slice of value."""

    id: str
    nexcoder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    tasks: list[Task] = Field(default_factory=list)
    estimate_hours: float = 0.0
    layer: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    recommended_agent: str | None = None
    labels: list[str] = Field(default_factory=list)

    @property
    def total_task_hours(self) -> float:
        """Return the sum of hours across all child tasks."""
        return sum(t.estimate_hours for t in self.tasks)


class Epic(BaseModel):
    """Top-level thematic feature or project initiative."""

    id: str
    nexcoder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    stories: list[Story] = Field(default_factory=list)
    layer: str | None = None
    labels: list[str] = Field(default_factory=list)

    @property
    def total_hours(self) -> float:
        """Return the sum of hours across all stories and tasks."""
        return sum(s.total_task_hours if s.tasks else s.estimate_hours for s in self.stories)


class Plan(BaseModel):
    """Complete backlog plan containing hierarchical epics, stories, and tasks."""

    title: str
    description: str = ""
    epics: list[Epic] = Field(default_factory=list)

    def all_stories(self) -> list[Story]:
        """Flatten and return all stories across all epics."""
        stories = []
        for epic in self.epics:
            stories.extend(epic.stories)
        return stories

    def all_tasks(self) -> list[Task]:
        """Flatten and return all tasks across all epics and stories."""
        tasks = []
        for story in self.all_stories():
            tasks.extend(story.tasks)
        return tasks

    def total_hours(self) -> float:
        """Calculate total estimated hours for all tasks."""
        return sum(task.estimate_hours for task in self.all_tasks())

    def find_task(self, task_id: str) -> Task | None:
        """Look up a task by its task ID."""
        for task in self.all_tasks():
            if task.id == task_id:
                return task
        return None

    def find_task_by_nexcoder_id(self, nexcoder_id: str) -> Task | None:
        """Look up a task by its unique nexcoder ID."""
        for task in self.all_tasks():
            if task.nexcoder_id == nexcoder_id:
                return task
        return None

    def validate_dependencies(self) -> list[str]:
        """Validate dependencies for missing references and cyclic dependency loops."""
        errors: list[str] = []
        all_task_ids = {t.id for t in self.all_tasks()}

        # 1. Missing dependency check
        for task in self.all_tasks():
            for dep in task.dependencies:
                if dep not in all_task_ids:
                    errors.append(f"Task '{task.id}' depends on non-existent task '{dep}'")

        # 2. Cycle detection via DFS
        graph: dict[str, list[str]] = {t.id: list(t.dependencies) for t in self.all_tasks()}
        visited: dict[str, int] = {}  # 0 = unvisited, 1 = visiting, 2 = visited

        def visit(node: str, path: list[str]) -> None:
            visited[node] = 1
            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    continue
                state = visited.get(neighbor, 0)
                if state == 1:
                    cycle = " -> ".join(path + [neighbor])
                    errors.append(f"Cyclic dependency detected: {cycle}")
                elif state == 0:
                    visit(neighbor, path + [neighbor])
            visited[node] = 2

        for task_id in graph:
            if visited.get(task_id, 0) == 0:
                visit(task_id, [task_id])

        return errors

    def topological_sort_tasks(self) -> list[Task]:
        """Return tasks ordered such that all dependencies appear before dependent tasks."""
        all_tasks_map = {t.id: t for t in self.all_tasks()}
        in_degree: dict[str, int] = {t.id: 0 for t in self.all_tasks()}
        dependents: dict[str, list[str]] = {t.id: [] for t in self.all_tasks()}

        for task in self.all_tasks():
            for dep in task.dependencies:
                if dep in all_tasks_map:
                    dependents[dep].append(task.id)
                    in_degree[task.id] += 1

        queue = [t.id for t in self.all_tasks() if in_degree[t.id] == 0]
        sorted_ids: list[str] = []

        while queue:
            current = queue.pop(0)
            sorted_ids.append(current)
            for child in dependents.get(current, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # In case of remaining nodes with unresolved cycle, append them at the end
        if len(sorted_ids) < len(all_tasks_map):
            remaining = [t.id for t in self.all_tasks() if t.id not in sorted_ids]
            sorted_ids.extend(remaining)

        return [all_tasks_map[tid] for tid in sorted_ids]
