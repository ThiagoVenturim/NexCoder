from __future__ import annotations

import contextlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, FindingCategory, Location, SBOMComponent, SBOMDocument
from faccoder_security.scanners.base import BaseScanner


class SyftScanner(BaseScanner):
    """Wrapper and offline SBOM generator for Syft (CycloneDX and SPDX)."""

    def __init__(self, executable_name: str = "syft") -> None:
        super().__init__(executable_name=executable_name, name="syft")

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> Any:
        start_time = time.perf_counter()
        target = Path(target_path)
        sbom_doc = self.generate_sbom(target, output_format="cyclonedx-json", force_offline=force_offline_fallback)

        findings: list[Finding] = []
        for comp in sbom_doc.components:
            if not comp.version or comp.version in ("*", "latest"):
                findings.append(
                    Finding(
                        id=f"syft-unpinned-{len(findings) + 1}",
                        scanner=self.name,
                        rule_id="syft.unpinned-dependency",
                        title=f"Unpinned dependency in SBOM: {comp.name}",
                        description=f"Component {comp.name} has no pinned version, leading to build non-determinism.",
                        category=FindingCategory.SCA,
                        location=Location(file_path=str(target), snippet=f"{comp.name}:{comp.version}"),
                    )
                )

        result = self._create_result(target, findings, start_time, version="syft-engine")
        if result.metadata:
            result.metadata.error_message = json.dumps({"component_count": len(sbom_doc.components)})
        return result

    def generate_sbom(
        self,
        target_path: str | Path,
        output_format: str = "cyclonedx-json",
        force_offline: bool = False,
    ) -> SBOMDocument:
        target = Path(target_path)

        if not force_offline and self.is_available():
            with contextlib.suppress(Exception):
                cmd = [self.executable_name, "packages", f"dir:{target}", "-o", output_format, "-q"]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.stdout.strip():
                    raw_text = proc.stdout
                    components: list[SBOMComponent] = []
                    data = json.loads(raw_text)
                    for art in data.get("artifacts", data.get("components", [])):
                        components.append(
                            SBOMComponent(
                                name=art.get("name", "unknown"),
                                version=art.get("version", ""),
                                purl=art.get("purl"),
                                component_type=art.get("type", "library"),
                            )
                        )
                    return SBOMDocument(
                        format=output_format,
                        schema_version="1.5",
                        components=components,
                        raw_content=raw_text,
                    )

        return self._offline_generate_sbom(target, output_format)

    def _offline_generate_sbom(self, target: Path, output_format: str) -> SBOMDocument:
        components: list[SBOMComponent] = []

        # Parse requirements.txt
        txt_files = [target] if target.is_file() and target.name.endswith(".txt") else list(target.rglob("*.txt"))
        for rfile in txt_files:
            if "requirements" in rfile.name:
                with contextlib.suppress(Exception):
                    for line in rfile.read_text(encoding="utf-8", errors="ignore").splitlines():
                        clean = line.strip().split("#")[0].strip()
                        m = re.match(r"^([a-zA-Z0-9_\-]+)\s*==\s*([0-9a-zA-Z\.\-]+)", clean)
                        if m:
                            name, ver = m.group(1), m.group(2)
                            components.append(
                                SBOMComponent(
                                    name=name,
                                    version=ver,
                                    purl=f"pkg:pypi/{name}@{ver}",
                                    component_type="library",
                                )
                            )

        # Parse pyproject.toml dependencies
        toml_files = (
            [target] if target.is_file() and target.name.endswith(".toml") else list(target.rglob("pyproject.toml"))
        )
        for pfile in toml_files:
            with contextlib.suppress(Exception):
                content = pfile.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    clean = line.strip().strip('"').strip("'").strip(",")
                    m = re.match(r"^([a-zA-Z0-9_\-]+)(?:>=|==|<=|~=|>|<)([0-9a-zA-Z\.\-]+)", clean)
                    if m:
                        name, ver = m.group(1), m.group(2)
                        components.append(
                            SBOMComponent(
                                name=name,
                                version=ver,
                                purl=f"pkg:pypi/{name}@{ver}",
                                component_type="library",
                            )
                        )

        # Parse package.json
        json_files = (
            [target]
            if target.is_file() and target.name.endswith("package.json")
            else list(target.rglob("package.json"))
        )
        for jfile in json_files:
            with contextlib.suppress(Exception):
                pkg_data = json.loads(jfile.read_text(encoding="utf-8", errors="ignore"))
                for group in ("dependencies", "devDependencies"):
                    for name, ver in pkg_data.get(group, {}).items():
                        ver_clean = re.sub(r"[\^~]", "", ver)
                        components.append(
                            SBOMComponent(
                                name=name,
                                version=ver_clean,
                                purl=f"pkg:npm/{name}@{ver_clean}",
                                component_type="library",
                            )
                        )

        unique: dict[tuple[str, str], SBOMComponent] = {}
        for c in components:
            unique[(c.name.lower(), c.version)] = c
        final_components = list(unique.values())

        raw_dict = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "component": {
                    "name": target.name or "project",
                    "type": "application",
                }
            },
            "components": [
                {
                    "type": c.component_type,
                    "name": c.name,
                    "version": c.version,
                    "purl": c.purl,
                }
                for c in final_components
            ],
        }

        return SBOMDocument(
            format=output_format,
            schema_version="1.5",
            components=final_components,
            raw_content=json.dumps(raw_dict, indent=2),
        )
