from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_security.agents.base import BaseSecurityAgent


class StrideCategory(enum.StrEnum):
    SPOOFING = "Spoofing"
    TAMPERING = "Tampering"
    REPUDIATION = "Repudiation"
    INFORMATION_DISCLOSURE = "Information Disclosure"
    DENIAL_OF_SERVICE = "Denial of Service"
    ELEVATION_OF_PRIVILEGE = "Elevation of Privilege"


class ComponentType(enum.StrEnum):
    PROCESS = "Process"
    DATA_STORE = "Data Store"
    DATA_FLOW = "Data Flow"
    EXTERNAL_ENTITY = "External Entity"


class DFDComponent(BaseModel):
    name: str
    component_type: ComponentType
    description: str = ""
    trust_boundary: str = "default"


class IdentifiedThreat(BaseModel):
    id: str
    component_name: str
    stride_category: StrideCategory
    title: str
    description: str
    impact: str
    likelihood: str = "Medium"
    mitigation: str


class ThreatModelResult(BaseModel):
    system_name: str
    summary: str
    components: list[DFDComponent] = Field(default_factory=list)
    threats: list[IdentifiedThreat] = Field(default_factory=list)


class ThreatModelAgent(BaseSecurityAgent):
    """sec-threat-model: threat modeling by data flow and architectural components (STRIDE)."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-threat-model",
            role="Specialist agent in architectural threat modeling using STRIDE and DFDs.",
        )

    def analyze(self, target: Any, offline: bool = True) -> ThreatModelResult:
        if isinstance(target, dict):
            system_name = target.get("name", "System")
            components_data = target.get("components", [])
            flows_data = target.get("flows", [])
        else:
            system_name = str(target)
            components_data = ["Web Frontend", "API Gateway", "Database"]
            flows_data = ["User -> API", "API -> DB"]

        components: list[DFDComponent] = []
        threats: list[IdentifiedThreat] = []

        # Analyze components
        for c in components_data:
            c_name = c if isinstance(c, str) else c.get("name", "Component")
            c_type = ComponentType.PROCESS
            if "db" in c_name.lower() or "database" in c_name.lower() or "store" in c_name.lower():
                c_type = ComponentType.DATA_STORE
            elif "user" in c_name.lower() or "client" in c_name.lower():
                c_type = ComponentType.EXTERNAL_ENTITY

            components.append(DFDComponent(name=c_name, component_type=c_type))

            # STRIDE threat generation for components
            if c_type == ComponentType.DATA_STORE:
                threats.append(
                    IdentifiedThreat(
                        id=f"TM-{len(threats) + 1}",
                        component_name=c_name,
                        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
                        title=f"Unauthorized access to sensitive data in {c_name}",
                        description=f"Direct query or leak of unencrypted data stored in {c_name}.",
                        impact="High",
                        likelihood="Medium",
                        mitigation=(
                            "Apply encryption at rest, principle of least privilege, and strict access controls."
                        ),
                    )
                )
                threats.append(
                    IdentifiedThreat(
                        id=f"TM-{len(threats) + 1}",
                        component_name=c_name,
                        stride_category=StrideCategory.TAMPERING,
                        title=f"Unauthorized modification of records in {c_name}",
                        description=f"Adversary alters integrity of persistent data in {c_name}.",
                        impact="High",
                        likelihood="Low",
                        mitigation="Implement immutable audit logging, transaction rollbacks, and schema constraints.",
                    )
                )
            elif c_type == ComponentType.PROCESS:
                threats.append(
                    IdentifiedThreat(
                        id=f"TM-{len(threats) + 1}",
                        component_name=c_name,
                        stride_category=StrideCategory.ELEVATION_OF_PRIVILEGE,
                        title=f"Privilege escalation via {c_name}",
                        description=(
                            f"Flaw in authorization logic allows horizontal or vertical escalation in {c_name}."
                        ),
                        impact="Critical",
                        likelihood="Medium",
                        mitigation="Enforce centralized authorization middleware and RBAC/ABAC verification.",
                    )
                )
                threats.append(
                    IdentifiedThreat(
                        id=f"TM-{len(threats) + 1}",
                        component_name=c_name,
                        stride_category=StrideCategory.DENIAL_OF_SERVICE,
                        title=f"Resource exhaustion in {c_name}",
                        description=f"Unbounded processing or request volume leads to downtime in {c_name}.",
                        impact="Medium",
                        likelihood="High",
                        mitigation="Implement rate limiting, timeouts, connection pooling, and circuit breakers.",
                    )
                )

        # Analyze flows
        for flow in flows_data:
            f_name = flow if isinstance(flow, str) else flow.get("name", "Flow")
            threats.append(
                IdentifiedThreat(
                    id=f"TM-{len(threats) + 1}",
                    component_name=f_name,
                    stride_category=StrideCategory.TAMPERING,
                    title=f"Man-in-the-middle tampering on flow {f_name}",
                    description=f"Interception and modification of in-transit payload along {f_name}.",
                    impact="High",
                    likelihood="Low",
                    mitigation="Mandate TLS 1.3 with strict certificate validation and mutual TLS where applicable.",
                )
            )

        return ThreatModelResult(
            system_name=system_name,
            summary=f"STRIDE Threat Model generated for {system_name} with {len(threats)} identified threats.",
            components=components,
            threats=threats,
        )
