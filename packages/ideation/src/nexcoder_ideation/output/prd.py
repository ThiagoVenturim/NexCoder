from __future__ import annotations

from faccoder_ideation.models import (
    ArchitectureProposal,
    HumanApprovalGate,
    JuryVerdict,
    ResearchSquadReport,
    StructuredIdea,
)


class PRDGenerator:
    """Generates structured Markdown PRD documents compatible with faccoder-planning converters."""

    @staticmethod
    def generate(
        idea: StructuredIdea,
        report: ResearchSquadReport,
        verdict: JuryVerdict,
        architecture: ArchitectureProposal,
        gate: HumanApprovalGate | None = None,
    ) -> str:
        """Render complete Markdown PRD document."""
        gate = gate or HumanApprovalGate()
        gate_status_str = gate.status.value.upper()

        lines: list[str] = [
            f"# PRD: {idea.title}",
            "",
            "## 1. Executive Summary & Value Hypothesis",
            "",
            f"**Summary**: {idea.summary}",
            "",
            f"- **Problem Statement**: {idea.value_hypothesis.problem_statement}",
            f"- **Proposed Solution**: {idea.value_hypothesis.proposed_solution}",
            f"- **Key Benefit**: {idea.value_hypothesis.key_benefit}",
            f"- **Core Metric**: {idea.value_hypothesis.primary_metric}",
            f"- **Differentiation Summary**: {idea.value_hypothesis.differentiation_summary}",
            "",
            "## 2. Target Audience Segments",
            "",
        ]

        for seg in idea.target_audience:
            lines.append(f"### Segment: {seg.name}")
            lines.append(f"- **Description**: {seg.description}")
            lines.append(f"- **Willingness to Pay**: {seg.willingness_to_pay}")
            if seg.pain_points:
                lines.append("- **Pain Points**:")
                for p in seg.pain_points:
                    lines.append(f"  - {p}")
            lines.append("")

        lines.extend(
            [
                "## 3. Market Diligence & Competitive Landscape",
                "",
                f"- **TAM Estimate**: {report.market.tam_estimate}",
                f"- **SAM Estimate**: {report.market.sam_estimate}",
                f"- **SOM Estimate**: {report.market.som_estimate}",
                f"- **CAGR**: {report.market.cagr_percentage or 'N/A'}%",
                "",
                "### Market Trends",
            ]
        )
        for trend in report.market.market_trends:
            lines.append(f"- {trend}")
        lines.append("")

        lines.append("### Direct Competitors")
        for comp in report.competitors.direct_competitors:
            lines.append(f"- **{comp.name}**: {', '.join(comp.strengths)} | Weaknesses: {', '.join(comp.weaknesses)}")
        lines.append("")

        lines.append("### Differentiation Matrix")
        lines.append("| Feature Dimension | Our Approach | Competitors | Advantage |")
        lines.append("|---|---|---|---|")
        for diff in report.differentiation.differentiation_matrix:
            row = (
                f"| {diff.feature_dimension} | {diff.our_approach} | "
                f"{diff.competitors_approach} | {diff.advantage_level} |"
            )
            lines.append(row)
        lines.append("")

        lines.extend(
            [
                "## 4. System Architecture & Technical Specifications",
                "",
                f"**System**: {architecture.system_name}",
                f"**Deployment Model**: {architecture.deployment_model}",
                "",
                f"**Data Flow**: {architecture.data_flow_description}",
                "",
                "### Core Components",
            ]
        )
        for comp in architecture.components:
            lines.append(f"#### Component: {comp.name}")
            lines.append(f"- **Purpose**: {comp.purpose}")
            lines.append(f"- **Technologies**: {', '.join(comp.technology_choices)}")
            if comp.data_stores:
                lines.append(f"- **Data Stores**: {', '.join(comp.data_stores)}")
            if comp.dependencies:
                lines.append(f"- **Dependencies**: {', '.join(comp.dependencies)}")
            lines.append("")

        lines.extend(
            [
                "### Security Controls",
            ]
        )
        for sc in architecture.security_controls:
            lines.append(f"- {sc}")
        lines.append("")

        lines.extend(
            [
                "## 5. Functional Requirements & Acceptance Criteria",
                "",
                "### Epic 1: Intake & Ingestion Subsystem",
                (
                    "- **Story**: As a user, I want to submit raw ideas in free text "
                    "so the system automatically extracts structured specifications."
                ),
                "  - **Scenario**: Successful idea structuring",
                "    - **Given** raw idea text with minimum 10 characters",
                "    - **When** the Idea Analyst processes the input",
                "    - **Then** problem, audience, and value hypothesis are generated without errors.",
                "",
                "### Epic 2: Multi-Agent Research Squad",
                (
                    "- **Story**: As a product manager, I want verified market and competitive "
                    "research with traceable citations."
                ),
                "  - **Scenario**: Research execution with offline fallback",
                "    - **Given** a structured idea",
                "    - **When** the research squad runs in offline mode",
                (
                    "    - **Then** all 7 specialists return valid findings and all citations "
                    "link to verified mock sources."
                ),
                "",
                "### Epic 3: b90 Committee & b85 Governance Gate",
                (
                    "- **Story**: As an engineering director, I want multi-stakeholder quorum consensus "
                    "and a human approval gate."
                ),
                "  - **Scenario**: Quorum approval",
                "    - **Given** completed research findings",
                "    - **When** 6 juror personas vote on the public rubric",
                (
                    "    - **Then** a quorum verdict of GO requires >= 60% agreement "
                    "before unlocking the human approval gate."
                ),
                "",
                "## 6. Verified Research Citations",
                "",
            ]
        )
        for src in report.all_sources:
            lines.append(f"- [{src.title}]({src.url}) - *{src.snippet[:120]}...* (Provider: {src.provider})")
        lines.append("")

        votes_summary = (
            f"**Vote Distribution**: {verdict.go_votes} GO, {verdict.pivot_votes} PIVOT, "
            f"{verdict.no_go_votes} NO-GO (Total: {verdict.total_jurors})"
        )
        lines.extend(
            [
                "## 7. b90 Jury Committee Verdict",
                "",
                f"**Verdict**: {verdict.verdict.value.upper()}",
                f"**Consensus Reached**: {verdict.consensus_reached}",
                votes_summary,
                f"**Summary**: {verdict.summary}",
                "",
                "### Average Rubric Scores",
            ]
        )
        for crit, score in verdict.average_scores.items():
            lines.append(f"- **{crit.capitalize()}**: {score} / 5.0")
        lines.append("")

        if verdict.dissenting_opinions:
            lines.append("### Dissenting Opinions")
            for diss in verdict.dissenting_opinions:
                lines.append(f"- {diss}")
            lines.append("")

        lines.extend(
            [
                "## 8. b85 Human Approval Gate",
                "",
                f"- **Status**: `{gate_status_str}`",
                f"- **Gate Required**: {gate.required}",
                f"- **Approved By**: {gate.approved_by or 'None'}",
                f"- **Approval Notes**: {gate.comments or 'Awaiting human authorization before planning handoff.'}",
                "",
                "<!-- faccoder-id: prd-" + idea.id + " -->",
            ]
        )

        return "\n".join(lines)
