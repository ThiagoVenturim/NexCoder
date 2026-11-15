"""nexcoder-security: Security scanners, specialist agents, and release gate for nexcoder."""

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
)

from nexcoder_security.gate import (
    GatePolicy,
    GateVerdict,
    SecurityGateEvaluator,
    generate_csp_header,
    generate_security_md,
    pin_dependencies,
    scaffold_app_security,
)
from nexcoder_security.models import (
    Finding,
    FindingCategory,
    Location,
    Remediation,
    SBOMComponent,
    SBOMDocument,
    ScanMetadata,
    ScanResult,
    Severity,
)
from nexcoder_security.reports import (
    OutdatedDependencyItem,
    ScannerCoverageItem,
    SecurityPostureMetrics,
    SecurityTrendPoint,
    build_security_nexdash_dataset,
    build_synthetic_security_scans,
    compute_security_metrics,
    generate_security_dashboard,
)
from nexcoder_security.scanners import (
    BanditScanner,
    BaseScanner,
    GitleaksScanner,
    MultiScannerEngine,
    OSVScanner,
    PipAuditScanner,
    SemgrepScanner,
    SyftScanner,
    TrivyScanner,
)

__all__ = [
    "BanditScanner",
    "BaseScanner",
    "Finding",
    "FindingCategory",
    "GatePolicy",
    "GateVerdict",
    "GitleaksScanner",
    "Location",
    "MultiScannerEngine",
    "OSVScanner",
    "OutdatedDependencyItem",
    "PipAuditScanner",
    "Remediation",
    "SBOMComponent",
    "SBOMDocument",
    "ScanMetadata",
    "ScanResult",
    "ScannerCoverageItem",
    "SecurityGateEvaluator",
    "SecurityPostureMetrics",
    "SecurityTrendPoint",
    "SemgrepScanner",
    "Severity",
    "SyftScanner",
    "TargetAuthorizationGate",
    "TargetAuthorizationRecord",
    "TargetNotAuthorizedError",
    "TrivyScanner",
    "build_security_nexdash_dataset",
    "build_synthetic_security_scans",
    "compute_security_metrics",
    "generate_csp_header",
    "generate_security_dashboard",
    "generate_security_md",
    "pin_dependencies",
    "scaffold_app_security",
]

__version__ = "0.1.0"
