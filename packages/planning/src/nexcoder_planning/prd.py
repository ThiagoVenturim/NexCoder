"""Converter from Product Requirements Documents (PRD) to structured backlogs."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from faccoder_core.prompts import load_prompt
from faccoder_core.structured import call_structured

from faccoder_planning.models import AcceptanceCriterion, Epic, Plan, Story, Task

PROMPTS_DIR = Path(__file__).parent / "prompts"


class PRDConverter:
    """Converts PRD markdown or plain text into structured Epics, Stories, and Tasks."""

    def parse_markdown(self, markdown_text: str, default_title: str = "Backlog Plan") -> Plan:
        """Deterministically parse a markdown PRD into a Plan hierarchy.

        Supports headers:
        - '# Epic: ...' or '# EP-01: ...' -> Epic
        - '## Story: ...' or '## US-01: ...' -> Story
        - '### Task: ...' or '### TSK-01: ...' -> Task

        Also parses task bullet attributes:
        - Layer: backend | frontend | data | qa | devops | security | core
        - Estimate: 4h | 8 hours | 2
        - Agent: backend-engineer
        - Depends on / Dependencies: TSK-01, TSK-02
        - Given ... / When ... / Then ... acceptance criteria
        """
        lines = markdown_text.splitlines()
        plan_title = default_title

        epics: list[Epic] = []
        current_epic: Epic | None = None
        current_story: Story | None = None
        current_task: Task | None = None

        epic_counter = 0
        story_counter = 0
        task_counter = 0

        current_given: str | None = None
        current_when: str | None = None

        def finalize_task() -> None:
            nonlocal current_given, current_when
            if current_given and current_when and current_task:
                # If trailing Given/When without Then, close it if possible
                pass
            current_given = None
            current_when = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check if root title is specified before any epic
            has_no_epic = not current_epic and "epic" not in stripped.lower()
            if stripped.startswith("# ") and has_no_epic and not re.search(r"\bEP-\d+", stripped, re.IGNORECASE):
                # Document title: strip leading '# ' and optional 'PRD:' prefix
                raw_title = stripped.lstrip("# ").strip()
                plan_title = re.sub(r"^(prd\s*[:\-]?\s*)", "", raw_title, flags=re.IGNORECASE).strip() or raw_title
                continue

            # Epic Header (# Epic: ... or # EP-01 ...)
            is_epic_h2 = stripped.startswith("## ") and not current_epic and "epic" in stripped.lower()
            if stripped.startswith("# ") or is_epic_h2:
                finalize_task()
                epic_counter += 1
                header_text = stripped.lstrip("# ").strip()
                clean_title = re.sub(
                    r"^(epic\s*[:\-]?\s*|\[?EP-\d+\]?\s*[:\-]?\s*)",
                    "",
                    header_text,
                    flags=re.IGNORECASE,
                ).strip()
                epic_id_match = re.search(r"\b(EP-\d+)\b", header_text, re.IGNORECASE)
                epic_id = epic_id_match.group(1).upper() if epic_id_match else f"EP-{epic_counter:02d}"

                current_epic = Epic(
                    id=epic_id,
                    title=clean_title or header_text,
                    stories=[],
                )
                epics.append(current_epic)
                current_story = None
                current_task = None
                continue

            # Story Header (## Story: ... or ## US-01 ...)
            is_story_h3 = stripped.startswith("### ") and not current_story and "story" in stripped.lower()
            if stripped.startswith("## ") or is_story_h3:
                finalize_task()
                if not current_epic:
                    epic_counter += 1
                    current_epic = Epic(id=f"EP-{epic_counter:02d}", title="General", stories=[])
                    epics.append(current_epic)

                story_counter += 1
                header_text = stripped.lstrip("# ").strip()
                clean_title = re.sub(
                    r"^(story\s*[:\-]?\s*|user\s*story\s*[:\-]?\s*|\[?US-\d+\]?\s*[:\-]?\s*)",
                    "",
                    header_text,
                    flags=re.IGNORECASE,
                ).strip()
                story_id_match = re.search(r"\b(US-\d+)\b", header_text, re.IGNORECASE)
                story_id = story_id_match.group(1).upper() if story_id_match else f"US-{story_counter:02d}"

                current_story = Story(
                    id=story_id,
                    title=clean_title or header_text,
                    tasks=[],
                )
                current_epic.stories.append(current_story)
                current_task = None
                continue

            # Task Header (### Task: ... or ### TSK-01 ...)
            if stripped.startswith("### ") or (stripped.startswith("#### ") and "task" in stripped.lower()):
                finalize_task()
                if not current_epic:
                    epic_counter += 1
                    current_epic = Epic(id=f"EP-{epic_counter:02d}", title="General", stories=[])
                    epics.append(current_epic)

                if not current_story:
                    story_counter += 1
                    current_story = Story(id=f"US-{story_counter:02d}", title=current_epic.title, tasks=[])
                    current_epic.stories.append(current_story)

                task_counter += 1
                header_text = stripped.lstrip("# ").strip()
                clean_title = re.sub(
                    r"^(task\s*[:\-]?\s*|\[?TSK-[\d-]+\]?\s*[:\-]?\s*)",
                    "",
                    header_text,
                    flags=re.IGNORECASE,
                ).strip()
                task_id_match = re.search(r"\b(TSK-[\w-]+)\b", header_text, re.IGNORECASE)
                task_id = task_id_match.group(1).upper() if task_id_match else f"TSK-{task_counter:02d}"

                current_task = Task(
                    id=task_id,
                    title=clean_title or header_text,
                    acceptance_criteria=[],
                )
                current_story.tasks.append(current_task)
                continue

            # If we are inside a Task, parse metadata & bullet attributes
            if current_task:
                # Acceptance criteria parsing
                given_match = re.search(r"(?:^[-*]\s*)?given\s*[:\-]?\s*(.+)$", stripped, re.IGNORECASE)
                when_match = re.search(r"(?:^[-*]\s*)?when\s*[:\-]?\s*(.+)$", stripped, re.IGNORECASE)
                then_match = re.search(r"(?:^[-*]\s*)?then\s*[:\-]?\s*(.+)$", stripped, re.IGNORECASE)

                if given_match:
                    current_given = given_match.group(1).strip()
                    continue
                if when_match:
                    current_when = when_match.group(1).strip()
                    continue
                if then_match:
                    then_text = then_match.group(1).strip()
                    if current_given and current_when:
                        current_task.acceptance_criteria.append(
                            AcceptanceCriterion(given=current_given, when=current_when, then=then_text)
                        )
                        current_given = None
                        current_when = None
                    else:
                        current_task.acceptance_criteria.append(
                            AcceptanceCriterion(given="System state is valid", when="Action occurs", then=then_text)
                        )
                    continue

                # Layer
                layer_match = re.search(r"(?:^[-*]\s*)?(?:layer|camada)\s*[:\-]\s*(\w+)", stripped, re.IGNORECASE)
                if layer_match:
                    current_task.layer = layer_match.group(1).lower().strip()
                    continue

                # Estimate
                est_pattern = (
                    r"(?:^[-*]\s*)?(?:estimate|estimativa|hours|horas)\s*[:\-]\s*([0-9.]+)\s*(?:h|hours|horas)?"
                )
                est_match = re.search(est_pattern, stripped, re.IGNORECASE)
                if not est_match:
                    est_match = re.search(r"\[([0-9.]+)\s*h\]", stripped, re.IGNORECASE)
                if est_match:
                    try:
                        current_task.estimate_hours = float(est_match.group(1))
                    except ValueError:
                        pass
                    continue

                # Recommended Agent
                agent_pattern = r"(?:^[-*]\s*)?(?:recommended\s+agent|agent|agente)\s*[:\-]\s*([\w\-]+)"
                agent_match = re.search(agent_pattern, stripped, re.IGNORECASE)
                if agent_match:
                    current_task.recommended_agent = agent_match.group(1).strip()
                    continue

                # Dependencies
                dep_pattern = r"(?:^[-*]\s*)?(?:depends\s+on|dependencies|dependencias|dep)\s*[:\-]\s*(.+)$"
                dep_match = re.search(dep_pattern, stripped, re.IGNORECASE)
                if dep_match:
                    raw_deps = dep_match.group(1)
                    deps = [d.strip().upper() for d in re.split(r"[,; ]+", raw_deps) if d.strip()]
                    for d in deps:
                        if d not in current_task.dependencies:
                            current_task.dependencies.append(d)
                    continue

                # Tags / Labels
                labels_match = re.search(r"(?:^[-*]\s*)?(?:labels|tags)\s*[:\-]\s*(.+)$", stripped, re.IGNORECASE)
                if labels_match:
                    raw_labels = labels_match.group(1)
                    labels = [lbl.strip().lower() for lbl in re.split(r"[,; ]+", raw_labels) if lbl.strip()]
                    for lbl in labels:
                        if lbl not in current_task.labels:
                            current_task.labels.append(lbl)
                    continue

                # Regular description lines
                if not stripped.startswith("-") and not stripped.startswith("*"):
                    if current_task.description:
                        current_task.description += "\n" + stripped
                    else:
                        current_task.description = stripped

        finalize_task()

        # If no epics were parsed (e.g. plain text or simple list), wrap into default structure
        if not epics and markdown_text.strip():
            epics.append(
                Epic(
                    id="EP-01",
                    title="Main Feature",
                    stories=[
                        Story(
                            id="US-01",
                            title="Primary Implementation",
                            tasks=[
                                Task(
                                    id="TSK-01",
                                    title=plan_title,
                                    description=markdown_text.strip(),
                                    estimate_hours=8.0,
                                )
                            ],
                        )
                    ],
                )
            )

        return Plan(title=plan_title, epics=epics)

    async def convert_with_llm(
        self,
        prd_text: str,
        *,
        llm: Any = None,
        context: str = "prd_to_plan",
    ) -> Plan:
        """Decompose PRD text into a structured Plan hierarchy using an LLM."""
        prompt_tmpl = load_prompt(PROMPTS_DIR, "prd_to_plan")
        system_msg, user_msg = prompt_tmpl.render(prd_text=prd_text)
        full_prompt = f"{system_msg}\n\n{user_msg}" if system_msg else user_msg

        plan: Plan = await call_structured(
            prompt=full_prompt,
            llm=llm,
            schema=Plan,
            context=context,
        )
        return plan

    def convert(
        self,
        prd_text: str,
        *,
        use_llm: bool = False,
        llm: Any = None,
    ) -> Plan:
        """Convert PRD text to Plan, routing either deterministically or via LLM."""
        if use_llm:
            return asyncio.run(self.convert_with_llm(prd_text, llm=llm))
        return self.parse_markdown(prd_text)
