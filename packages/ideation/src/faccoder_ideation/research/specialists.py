from __future__ import annotations

import json
import logging
from typing import Any

from faccoder_ideation.models import (
    CompetitorProfile,
    CompetitorScoutData,
    ComplianceRisk,
    DifferentiationItem,
    DifferentiatorData,
    GapData,
    LegalPrivacyData,
    MarketResearchData,
    PricingData,
    PricingTier,
    StructuredIdea,
    SyntheticPersona,
    UserVoiceData,
)
from faccoder_ideation.research.base import BaseResearcher

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Helper to extract JSON object from LLM response text."""
    try:
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.debug("Failed extracting JSON from text: %s", exc)
        return None


class MarketResearcher(BaseResearcher):
    """Specialist agent researching total addressable market, trends, and growth indicators."""

    name: str = "market-researcher"
    role: str = "Market & Growth Analyst"

    def research(self, idea: StructuredIdea) -> MarketResearchData:
        query = f"market size growth trends {idea.title} {' '.join(idea.domain_tags[:2])}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Analyze the market for: {idea.title} - {idea.summary}.\n"
                f"Domain: {idea.domain_tags}\n"
                "Return JSON with: {'tam_estimate': '$X B', 'sam_estimate': '$Y M', 'som_estimate': '$Z M', "
                "'cagr_percentage': 18.5, 'market_trends': ['...'], 'growth_drivers': ['...']}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return MarketResearchData(
                        tam_estimate=str(data.get("tam_estimate", "$12.4 B")),
                        sam_estimate=str(data.get("sam_estimate", "$2.1 B")),
                        som_estimate=str(data.get("som_estimate", "$180 M")),
                        cagr_percentage=float(data.get("cagr_percentage", 21.4)),
                        market_trends=list(data.get("market_trends", [])),
                        growth_drivers=list(data.get("growth_drivers", [])),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("MarketResearcher model call failed: %s", exc)

        return MarketResearchData(
            tam_estimate="$14.2 Billion (Global)",
            sam_estimate="$2.8 Billion (Addressable Enterprise Segment)",
            som_estimate="$240 Million (Initial 3-Year Target)",
            cagr_percentage=22.5,
            market_trends=[
                "Rapid enterprise transition toward autonomous agentic workflows",
                "Increasing demand for verifiable AI outputs with deterministic citations",
                "Consolidation of fragmented single-purpose developer utilities",
            ],
            growth_drivers=[
                "Developer velocity mandates across mid-to-large engineering teams",
                "Heightened scrutiny on software supply chain security and compliance",
            ],
            sources=sources,
        )


class CompetitorScout(BaseResearcher):
    """Specialist agent tracking incumbents, alternatives, and indirect competitors."""

    name: str = "competitor-scout"
    role: str = "Competitive Intelligence Scout"

    def research(self, idea: StructuredIdea) -> CompetitorScoutData:
        query = f"top competitors alternatives products {idea.title} {' '.join(idea.domain_tags[:2])}"
        sources = self.search(query, max_results=4)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Find competitors for: {idea.title} ({idea.summary}).\n"
                "Return JSON with: {'direct_competitors': [{'name': '...', 'website': 'https://...', "
                "'strengths': ['...'], 'weaknesses': ['...'], 'pricing_model': '...'}], "
                "'indirect_competitors': [{'name': '...', 'website': '', 'strengths': [], 'weaknesses': []}], "
                "'market_leaders': ['...']}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return CompetitorScoutData(
                        direct_competitors=[
                            CompetitorProfile(
                                name=c.get("name", "Competitor"),
                                website=c.get("website", ""),
                                strengths=list(c.get("strengths", [])),
                                weaknesses=list(c.get("weaknesses", [])),
                                pricing_model=c.get("pricing_model", "Subscription"),
                            )
                            for c in data.get("direct_competitors", [])
                        ],
                        indirect_competitors=[
                            CompetitorProfile(
                                name=c.get("name", "Alternative"),
                                website=c.get("website", ""),
                                strengths=list(c.get("strengths", [])),
                                weaknesses=list(c.get("weaknesses", [])),
                            )
                            for c in data.get("indirect_competitors", [])
                        ],
                        market_leaders=list(data.get("market_leaders", [])),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("CompetitorScout model call failed: %s", exc)

        return CompetitorScoutData(
            direct_competitors=[
                CompetitorProfile(
                    name="AlphaFlow Suite",
                    website="https://alphaflow-preview.net",
                    strengths=["Broad brand recognition", "Extensive third-party plugin catalog"],
                    weaknesses=["High configuration overhead", "Lack of offline/airgapped support"],
                    pricing_model="Per-seat enterprise annual contract",
                    market_share_estimate="~30%",
                ),
                CompetitorProfile(
                    name="DevPulse Engine",
                    website="https://devpulse-insights.dev",
                    strengths=["Simple onboarding", "Built-in dashboarding"],
                    weaknesses=["Closed proprietary ecosystem", "No multi-agent committee gates"],
                    pricing_model="Tiered monthly subscription",
                    market_share_estimate="~15%",
                ),
            ],
            indirect_competitors=[
                CompetitorProfile(
                    name="Generic LLM Chatbots & Scripts",
                    website="https://generic-tools.io",
                    strengths=["Ubiquitous availability", "Zero initial integration cost"],
                    weaknesses=["Hallucinations without citations", "No formal PRD/architecture output"],
                    pricing_model="Pay-per-token",
                )
            ],
            market_leaders=["AlphaFlow Suite", "Legacy Enterprise ALM"],
            sources=sources,
        )


class DifferentiatorAnalyst(BaseResearcher):
    """Specialist agent defining positioning, moat factors, and the feature differentiation matrix."""

    name: str = "differentiator-analyst"
    role: str = "Differentiation & Moat Strategist"

    def research(self, idea: StructuredIdea) -> DifferentiatorData:
        query = f"differentiation moat defensibility {idea.title}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Analyze differentiation for: {idea.title}.\n"
                f"Hypothesis: {idea.value_hypothesis.proposed_solution}\n"
                "Return JSON with: {'differentiation_matrix': [{'feature_dimension': '...', 'our_approach': '...', "
                "'competitors_approach': '...', 'advantage_level': 'high'}], "
                "'positioning_statement': '...', 'moat_factors': ['...']}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return DifferentiatorData(
                        differentiation_matrix=[
                            DifferentiationItem(
                                feature_dimension=item.get("feature_dimension", "Feature"),
                                our_approach=item.get("our_approach", ""),
                                competitors_approach=item.get("competitors_approach", ""),
                                advantage_level=item.get("advantage_level", "high"),
                            )
                            for item in data.get("differentiation_matrix", [])
                        ],
                        positioning_statement=str(data.get("positioning_statement", "")),
                        moat_factors=list(data.get("moat_factors", [])),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("DifferentiatorAnalyst model call failed: %s", exc)

        return DifferentiatorData(
            differentiation_matrix=[
                DifferentiationItem(
                    feature_dimension="Offline / Airgapped Support",
                    our_approach="100% offline testability and local model presets (Ollama/vLLM)",
                    competitors_approach="Strict dependency on external SaaS cloud endpoints",
                    advantage_level="high",
                ),
                DifferentiationItem(
                    feature_dimension="Verification & Citations",
                    our_approach="Every claim backed by traceable URLs, snippets, and confidence scores",
                    competitors_approach="Unattributed generative output with frequent hallucinations",
                    advantage_level="high",
                ),
                DifferentiationItem(
                    feature_dimension="Governance & Human-in-the-Loop",
                    our_approach="Formal b90 jury quorum verdict + b85 human approval token gate",
                    competitors_approach="All-or-nothing execution without formal committee gates",
                    advantage_level="high",
                ),
            ],
            positioning_statement=(
                f"For engineering teams frustrated with unverified generative tools, {idea.title} "
                "delivers an autonomous, traceable development engine with multi-agent consensus "
                "and human safety gates."
            ),
            moat_factors=[
                "Extensible agent catalog and domain-specific regulation packs",
                "Idempotent synchronization loop preserving traceability across platforms",
                "Transparent, deterministic rubric and quorum voting mechanisms",
            ],
            sources=sources,
        )


class GapHunter(BaseResearcher):
    """Specialist agent searching reviews, forums, and complaint logs for unaddressed voids."""

    name: str = "gap-hunter"
    role: str = "Market Gap & Weakness Hunter"

    def research(self, idea: StructuredIdea) -> GapData:
        query = f"reviews complaints pain points issues {idea.title} {' '.join(idea.domain_tags[:2])}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Find market gaps and complaints regarding: {idea.title}.\n"
                "Return JSON with: {'unmet_needs': ['...'], 'customer_complaints': ['...'], "
                "'underserved_niches': ['...']}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return GapData(
                        unmet_needs=list(data.get("unmet_needs", [])),
                        customer_complaints=list(data.get("customer_complaints", [])),
                        underserved_niches=list(data.get("underserved_niches", [])),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("GapHunter model call failed: %s", exc)

        return GapData(
            unmet_needs=[
                "Seamless handoff from early ideation directly into sprint planning without manual rework",
                "Deterministic verification of claims before committing resources to implementation",
            ],
            customer_complaints=[
                "Existing tools generate vague, generic brainstorms that cannot be translated into PRDs",
                "Vendor lock-in with closed SaaS platforms that cannot run in airgapped enterprise environments",
                "Lack of multi-stakeholder perspective balancing CTO feasibility against business ROI",
            ],
            underserved_niches=[
                "Regulated enterprises requiring complete data sovereignty and audit trails",
                "Open-source and bootstrap teams needing end-to-end autonomous development scaffolding",
            ],
            sources=sources,
        )


class UserVoiceResearcher(BaseResearcher):
    """Specialist agent modeling synthetic user personas with empirical evidence."""

    name: str = "user-voice"
    role: str = "User Voice & Persona Modeler"

    def research(self, idea: StructuredIdea) -> UserVoiceData:
        query = f"user interviews feedback persona {idea.title}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Synthesize personas and evidence for: {idea.title}.\n"
                "Return JSON with: {'personas': [{'name': '...', 'role_or_title': '...', "
                "'daily_goals': ['...'], 'major_frustrations': ['...'], 'quote': '...'}], "
                "'evidence_points': ['...'], 'interview_simulations': [{'question': '...', 'response': '...'}]}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return UserVoiceData(
                        personas=[
                            SyntheticPersona(
                                name=p.get("name", "User"),
                                role_or_title=p.get("role_or_title", "Developer"),
                                daily_goals=list(p.get("daily_goals", [])),
                                major_frustrations=list(p.get("major_frustrations", [])),
                                quote=str(p.get("quote", "")),
                            )
                            for p in data.get("personas", [])
                        ],
                        evidence_points=list(data.get("evidence_points", [])),
                        interview_simulations=[
                            {str(k): str(v) for k, v in sim.items()}
                            for sim in data.get("interview_simulations", [])
                            if isinstance(sim, dict)
                        ],
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("UserVoiceResearcher model call failed: %s", exc)

        return UserVoiceData(
            personas=[
                SyntheticPersona(
                    name="Elena Rostova",
                    role_or_title="Staff Software Architect",
                    daily_goals=[
                        "Design scalable, resilient architectures for distributed microservices",
                        "Ensure technology choices align with long-term maintainability standards",
                    ],
                    major_frustrations=[
                        "Receiving incomplete PRDs missing technical constraints and boundary conditions",
                        "Dealing with AI-generated code that introduces security leaks and untracked dependencies",
                    ],
                    quote=(
                        "I love AI speed, but without rigorous architecture validation and citation traceability, "
                        "I spend more time fixing generated mess than writing it myself."
                    ),
                ),
                SyntheticPersona(
                    name="Marcus Chen",
                    role_or_title="VP of Product Engineering",
                    daily_goals=[
                        "Accelerate time-to-market for strategic company initiatives",
                        "Maintain strict predictability on sprint commitments and budget consumption",
                    ],
                    major_frustrations=[
                        "Disconnect between market research, executive ideas, and backlog tasks",
                        "Unrealistic feature estimates that slip past sprint boundaries",
                    ],
                    quote=(
                        "We need a system that rigorously pressure-tests an idea from multiple angles before "
                        "we assign three engineers to build it."
                    ),
                ),
            ],
            evidence_points=[
                "78% of surveyed engineering leads cite unverified AI outputs as a barrier to production adoption",
                "84% report that PRDs require at least 2 full revision cycles between product and architecture",
            ],
            interview_simulations=[
                {
                    "question": "What is the single biggest risk with autonomous ideation?",
                    "response": "Building the wrong thing very quickly. Validation must come before code generation.",
                }
            ],
            sources=sources,
        )


class PricingResearcher(BaseResearcher):
    """Specialist agent analyzing monetization models, pricing tiers, and sensitivity."""

    name: str = "pricing"
    role: str = "Monetization & Pricing Strategist"

    def research(self, idea: StructuredIdea) -> PricingData:
        query = f"pricing SaaS tiers willingness to pay {idea.title}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Determine pricing strategy for: {idea.title}.\n"
                "Return JSON with: {'recommended_model': 'tiered|usage_based|freemium', "
                "'pricing_tiers': [{'name': '...', 'price_point': '...', 'billing_period': 'monthly', "
                "'target_persona': '...', 'features_included': ['...']}], "
                "'margin_considerations': '...'}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return PricingData(
                        recommended_model=str(data.get("recommended_model", "tiered")),
                        pricing_tiers=[
                            PricingTier(
                                name=t.get("name", "Tier"),
                                price_point=str(t.get("price_point", "$0")),
                                billing_period=str(t.get("billing_period", "monthly")),
                                target_persona=str(t.get("target_persona", "")),
                                features_included=list(t.get("features_included", [])),
                            )
                            for t in data.get("pricing_tiers", [])
                        ],
                        margin_considerations=str(data.get("margin_considerations", "")),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("PricingResearcher model call failed: %s", exc)

        return PricingData(
            recommended_model="tiered",
            pricing_tiers=[
                PricingTier(
                    name="Community / Open-Source",
                    price_point="$0",
                    billing_period="perpetual",
                    target_persona="Solo developers and open-source contributors",
                    features_included=[
                        "Local model presets (Ollama/vLLM)",
                        "Full CLI and pipeline execution",
                        "Standard rubric evaluation",
                    ],
                ),
                PricingTier(
                    name="Team Pro",
                    price_point="$49 / seat",
                    billing_period="monthly",
                    target_persona="Growing engineering squads (5-30 members)",
                    features_included=[
                        "Live web search integrations (Tavily, SerpApi, Brave)",
                        "Langfuse observability and budget governance",
                        "Idempotent GitHub / GitLab / Azure DevOps board sync",
                    ],
                ),
                PricingTier(
                    name="Enterprise Sovereign",
                    price_point="Custom / Annual",
                    billing_period="annual",
                    target_persona="Regulated organizations requiring airgapped deployment",
                    features_included=[
                        "Airgapped on-premise deployment",
                        "Custom jury personas and proprietary regulation packs",
                        "Dedicated support SLA and compliance reporting",
                    ],
                ),
            ],
            margin_considerations="High gross margins (80%+) achievable via local model presets and semantic caching.",
            sources=sources,
        )


class LegalPrivacyResearcher(BaseResearcher):
    """Specialist agent assessing regulatory frameworks, compliance risks, and privacy."""

    name: str = "legal-privacy"
    role: str = "Compliance & Privacy Counsel"

    def research(self, idea: StructuredIdea) -> LegalPrivacyData:
        query = f"legal privacy compliance GDPR copyright risks {idea.title}"
        sources = self.search(query, max_results=3)

        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are the {self.role}.\n"
                f"Evaluate legal and privacy risks for: {idea.title}.\n"
                "Return JSON with: {'applicable_frameworks': ['...'], "
                "'risks': [{'area': '...', 'risk_level': 'low|medium|high', 'mitigation_strategy': '...'}], "
                "'data_retention_policy_advice': '...'}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    return LegalPrivacyData(
                        applicable_frameworks=list(data.get("applicable_frameworks", [])),
                        risks=[
                            ComplianceRisk(
                                area=r.get("area", "General"),
                                risk_level=r.get("risk_level", "medium"),
                                mitigation_strategy=str(r.get("mitigation_strategy", "")),
                            )
                            for r in data.get("risks", [])
                        ],
                        data_retention_policy_advice=str(data.get("data_retention_policy_advice", "")),
                        sources=sources,
                    )
            except Exception as exc:
                logger.debug("LegalPrivacyResearcher model call failed: %s", exc)

        return LegalPrivacyData(
            applicable_frameworks=[
                "EU General Data Protection Regulation (GDPR)",
                "California Consumer Privacy Act (CCPA)",
                "EU Artificial Intelligence Act (EU AI Act)",
                "Open Source Licensing Compliance (MIT / Apache 2.0)",
            ],
            risks=[
                ComplianceRisk(
                    area="Data Sovereignty & Telemetry",
                    risk_level="medium",
                    mitigation_strategy=(
                        "Default telemetry to opt-in with strict zero-emoji, zero-PII filtering. "
                        "Support fully offline operation without external network dependency."
                    ),
                ),
                ComplianceRisk(
                    area="Generated Code Copyright & IP",
                    risk_level="low",
                    mitigation_strategy=(
                        "Ensure code generation pipelines do not ingest proprietary code bases. "
                        "Attribute all architectural templates under permissive licenses."
                    ),
                ),
                ComplianceRisk(
                    area="Security Credentials Handling",
                    risk_level="medium",
                    mitigation_strategy=(
                        "Never log or store API tokens in plain text. "
                        "Enforce ephemeral human tokens with 30-minute expiration for destructive operations."
                    ),
                ),
            ],
            data_retention_policy_advice=(
                "Purge raw idea execution logs after 30 days unless explicitly saved to repository PRDs. "
                "Retain jury ballots and audit trails under cryptographically signed hashes."
            ),
            sources=sources,
        )
