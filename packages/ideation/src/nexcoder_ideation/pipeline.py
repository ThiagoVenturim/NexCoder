from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from faccoder_ideation.intake import IdeaAnalyst
from faccoder_ideation.jury.committee import JuryCommittee
from faccoder_ideation.models import (
    IdeationOutput,
    RawIdea,
)
from faccoder_ideation.output.architecture import ArchitectureDesigner
from faccoder_ideation.output.gate import HumanGateManager
from faccoder_ideation.output.prd import PRDGenerator
from faccoder_ideation.output.report import ReportGenerator
from faccoder_ideation.research.squad import ResearchSquad
from faccoder_ideation.search.base import SearchProvider
from faccoder_ideation.search.providers import get_search_provider

logger = logging.getLogger(__name__)


class IdeationPipeline:
    """Full end-to-end ideation pipeline orchestrating intake, squad research, b90 jury, and deliverable reports."""

    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        model: Any = None,
        quorum_threshold: float = 0.6,
        allow_network: bool = False,
    ) -> None:
        self.search_provider = search_provider or get_search_provider(allow_network=allow_network)
        self.model = model
        self.quorum_threshold = quorum_threshold

        self.analyst = IdeaAnalyst(model=self.model)
        self.squad = ResearchSquad(search_provider=self.search_provider, model=self.model)
        self.committee = JuryCommittee(quorum_threshold=self.quorum_threshold, model=self.model)
        self.architect = ArchitectureDesigner(model=self.model)
        self.gate_manager = HumanGateManager()

    def run(
        self,
        raw_idea: str | RawIdea,
        dry_run: bool = False,
    ) -> tuple[IdeationOutput, str]:
        """Execute the end-to-end ideation workflow and return (IdeationOutput, approval_secret)."""
        logger.info("Initiating IdeationPipeline run...")

        # 1. Intake
        structured_idea = self.analyst.analyze(raw_idea)

        # 2. Research Squad Diligence
        research_report = self.squad.run(structured_idea)

        # 3. b90 Jury Committee Evaluation
        verdict = self.committee.evaluate(structured_idea, research_report)

        # 4. Architecture Proposal
        architecture = self.architect.design(structured_idea, research_report)

        # 5. b85 Human Gate Setup
        gate, secret = self.gate_manager.create_gate(structured_idea.id, dry_run=dry_run)

        # 6. Deliverable Document Rendering
        PRDGenerator.generate(
            idea=structured_idea,
            report=research_report,
            verdict=verdict,
            architecture=architecture,
            gate=gate,
        )
        md_report = ReportGenerator.generate_markdown(
            idea=structured_idea,
            report=research_report,
            verdict=verdict,
            architecture=architecture,
            gate=gate,
        )
        html_report = ReportGenerator.generate_html(
            idea=structured_idea,
            report=research_report,
            verdict=verdict,
            architecture=architecture,
            gate=gate,
        )

        output = IdeationOutput(
            structured_idea=structured_idea,
            research_report=research_report,
            jury_verdict=verdict,
            architecture=architecture,
            approval_gate=gate,
            markdown_report=md_report,
            html_report=html_report,
        )

        logger.info(
            "IdeationPipeline completed. Idea ID: %s, Verdict: %s, Gate required: %s",
            structured_idea.id,
            verdict.verdict.value,
            gate.required,
        )
        return output, secret

    def approve_gate(
        self,
        output: IdeationOutput,
        token_or_secret: str,
        approver: str = "human-operator",
        comments: str = "",
    ) -> bool:
        """Authorize the b85 human approval gate for the deliverable."""
        success = self.gate_manager.approve(
            gate=output.approval_gate,
            provided_token=token_or_secret,
            approver=approver,
            comments=comments,
        )
        if success:
            # Re-render PRD and reports with approved status
            output.markdown_report = ReportGenerator.generate_markdown(
                idea=output.structured_idea,
                report=output.research_report,
                verdict=output.jury_verdict,
                architecture=output.architecture,
                gate=output.approval_gate,
            )
            output.html_report = ReportGenerator.generate_html(
                idea=output.structured_idea,
                report=output.research_report,
                verdict=output.jury_verdict,
                architecture=output.architecture,
                gate=output.approval_gate,
            )
        return success

    @staticmethod
    def save_deliverables(output: IdeationOutput, target_dir: str | Path) -> dict[str, Path]:
        """Write all generated deliverable artifacts to the designated target directory."""
        dest = Path(target_dir)
        dest.mkdir(parents=True, exist_ok=True)

        prd_path = dest / "prd.md"
        report_md_path = dest / "report.md"
        report_html_path = dest / "report.html"
        idea_json_path = dest / "structured_idea.json"
        verdict_json_path = dest / "jury_verdict.json"

        prd_path.write_text(
            PRDGenerator.generate(
                idea=output.structured_idea,
                report=output.research_report,
                verdict=output.jury_verdict,
                architecture=output.architecture,
                gate=output.approval_gate,
            ),
            encoding="utf-8",
        )
        report_md_path.write_text(output.markdown_report, encoding="utf-8")
        report_html_path.write_text(output.html_report, encoding="utf-8")
        idea_json_path.write_text(output.structured_idea.model_dump_json(indent=2), encoding="utf-8")
        verdict_json_path.write_text(output.jury_verdict.model_dump_json(indent=2), encoding="utf-8")

        return {
            "prd": prd_path,
            "report_md": report_md_path,
            "report_html": report_html_path,
            "idea_json": idea_json_path,
            "verdict_json": verdict_json_path,
        }
