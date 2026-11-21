from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexcoder_security.agents.base import BaseSecurityAgent
from nexcoder_security.models import Finding


class SecretRemediationStep(BaseModel):
    step_number: int
    action: str
    target: str
    urgency: str = "Immediate"


class ExposedSecretAssessment(BaseModel):
    finding_id: str
    secret_type: str
    file_path: str
    line_number: int | None = None
    exposure_risk: str
    rotation_plan: list[SecretRemediationStep] = Field(default_factory=list)


class SecretsAnalysisResult(BaseModel):
    secrets_detected: int
    critical_exposures: int
    assessments: list[ExposedSecretAssessment] = Field(default_factory=list)


class SecretsAgent(BaseSecurityAgent):
    """sec-secrets: analyzes exposed credentials, keys and certificates, generating immediate revocation plans."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-secrets",
            role="Specialist agent in secrets detection, cryptographic entropy analysis, and rotation procedures.",
        )

    def analyze(self, target: Any, offline: bool = True) -> SecretsAnalysisResult:
        findings: list[Finding] = (
            target if isinstance(target, list) else target.findings if hasattr(target, "findings") else []
        )

        assessments: list[ExposedSecretAssessment] = []
        critical_count = 0

        for f in findings:
            if f.category.value != "secret":
                continue

            sec_type = f.title.replace("Secret detected:", "").strip()
            loc_file = f.location.file_path if f.location else "unknown"
            loc_line = f.location.line_start if f.location else None

            if f.severity.value in ("critical", "high"):
                critical_count += 1

            steps = [
                SecretRemediationStep(
                    step_number=1,
                    action=f"Revoke credential '{sec_type}' immediately in the provider dashboard/IAM.",
                    target=sec_type,
                    urgency="Immediate",
                ),
                SecretRemediationStep(
                    step_number=2,
                    action="Provision a replacement key and store it in an encrypted environment variable or Vault.",
                    target="Environment/Secrets Manager",
                    urgency="Immediate",
                ),
                SecretRemediationStep(
                    step_number=3,
                    action=(f"Remove the hardcoded secret from {loc_file} and verify git history does not leak it."),
                    target=loc_file,
                    urgency="High",
                ),
            ]

            assessments.append(
                ExposedSecretAssessment(
                    finding_id=f.id,
                    secret_type=sec_type,
                    file_path=loc_file,
                    line_number=loc_line,
                    exposure_risk="Critical exposure requiring immediate revocation and credential rollover.",
                    rotation_plan=steps,
                )
            )

        return SecretsAnalysisResult(
            secrets_detected=len(assessments),
            critical_exposures=critical_count,
            assessments=assessments,
        )
