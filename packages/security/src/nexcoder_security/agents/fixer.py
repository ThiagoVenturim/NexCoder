from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexcoder_security.agents.base import BaseSecurityAgent
from nexcoder_security.models import Finding


class SurgicalPatch(BaseModel):
    finding_id: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    original_code: str
    fixed_code: str
    diff_patch: str
    explanation: str
    safety_notes: str


class FixerResult(BaseModel):
    total_findings_considered: int
    patches_generated: int
    patches: list[SurgicalPatch] = Field(default_factory=list)


class SecurityFixerAgent(BaseSecurityAgent):
    """sec-fixer: generates precise, surgical remediation diffs and patches for identified vulnerabilities."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-fixer",
            role="Specialist agent in generating surgical code patches, AST refactoring, and secure remediations.",
        )

    def analyze(self, target: Any, offline: bool = True) -> FixerResult:
        findings: list[Finding] = (
            target if isinstance(target, list) else target.findings if hasattr(target, "findings") else []
        )

        patches: list[SurgicalPatch] = []

        for f in findings:
            snippet = f.location.snippet if f.location and f.location.snippet else ""
            loc_file = f.location.file_path if f.location else "unknown.py"
            loc_line = f.location.line_start if f.location else 1

            if "shell-true" in f.rule_id.lower() or "b602" in f.rule_id.lower():
                orig = snippet or "subprocess.call(cmd, shell=True)"
                fixed = "subprocess.run(shlex.split(cmd), check=True)  # shell=False (safe)"
                diff = f"--- a/{loc_file}\n+++ b/{loc_file}\n@@ -{loc_line},1 +{loc_line},1 @@\n-{orig}\n+{fixed}\n"
                patches.append(
                    SurgicalPatch(
                        finding_id=f.id,
                        file_path=loc_file,
                        line_start=loc_line,
                        line_end=loc_line,
                        original_code=orig,
                        fixed_code=fixed,
                        diff_patch=diff,
                        explanation="Replaced shell=True invocation with argument list parsing using shlex.split().",
                        safety_notes=(
                            "Verify that no shell metacharacters or built-in shell features were relied upon."
                        ),
                    )
                )
            elif "exec" in f.rule_id.lower() or "eval" in f.rule_id.lower():
                orig = snippet or "eval(user_expression)"
                fixed = "ast.literal_eval(user_expression)  # Safe literal evaluation"
                diff = f"--- a/{loc_file}\n+++ b/{loc_file}\n@@ -{loc_line},1 +{loc_line},1 @@\n-{orig}\n+{fixed}\n"
                patches.append(
                    SurgicalPatch(
                        finding_id=f.id,
                        file_path=loc_file,
                        line_start=loc_line,
                        line_end=loc_line,
                        original_code=orig,
                        fixed_code=fixed,
                        diff_patch=diff,
                        explanation="Replaced unsafe dynamic eval with ast.literal_eval.",
                        safety_notes=(
                            "ast.literal_eval only parses Python literal structures "
                            "(strings, numbers, tuples, dicts, booleans, and None)."
                        ),
                    )
                )
            elif f.category.value == "secret":
                orig = snippet or 'API_KEY = "AKIA1234567890ABCDEF"'
                fixed = 'API_KEY = os.environ.get("API_KEY")'
                diff = f"--- a/{loc_file}\n+++ b/{loc_file}\n@@ -{loc_line},1 +{loc_line},1 @@\n-{orig}\n+{fixed}\n"
                patches.append(
                    SurgicalPatch(
                        finding_id=f.id,
                        file_path=loc_file,
                        line_start=loc_line,
                        line_end=loc_line,
                        original_code=orig,
                        fixed_code=fixed,
                        diff_patch=diff,
                        explanation="Migrated hardcoded plaintext secret to environment variable lookup.",
                        safety_notes="Ensure the environment variable is configured in deployment environment.",
                    )
                )

        return FixerResult(
            total_findings_considered=len(findings),
            patches_generated=len(patches),
            patches=patches,
        )
