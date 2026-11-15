"""Code quality and architecture review: detectors, prioritized report and gated reviewer."""

from __future__ import annotations

from nexcoder_agents.quality.detectors import (
    cyclomatic_complexity,
    detect_branch_issues,
    detect_data_modeling_issues,
    detect_duplicate_functions,
    detect_over_engineering,
    detect_performance_smells,
    detect_readability_issues,
    detect_structure_issues,
    detect_temporary_solutions,
    detect_useless_wrappers,
    max_nesting_depth,
    normalize_code_tokens,
    run_quality_detectors,
    token_similarity,
)
from nexcoder_agents.quality.models import (
    BranchInfo,
    QualityCategory,
    QualityFinding,
    QualityReport,
    QualitySeverity,
    QualityThresholds,
    sort_findings,
)
from nexcoder_agents.quality.review import (
    APPROVAL_TOKEN_INPUT_KEY,
    QUALITY_REVIEW_MODE,
    QualityReviewBlock,
    QualityReviewer,
    collect_git_branches,
)
from nexcoder_agents.quality.snapshot import ProjectSnapshot, is_test_path

__all__ = [
    "APPROVAL_TOKEN_INPUT_KEY",
    "QUALITY_REVIEW_MODE",
    "BranchInfo",
    "ProjectSnapshot",
    "QualityCategory",
    "QualityFinding",
    "QualityReport",
    "QualityReviewBlock",
    "QualityReviewer",
    "QualitySeverity",
    "QualityThresholds",
    "collect_git_branches",
    "cyclomatic_complexity",
    "detect_branch_issues",
    "detect_data_modeling_issues",
    "detect_duplicate_functions",
    "detect_over_engineering",
    "detect_performance_smells",
    "detect_readability_issues",
    "detect_structure_issues",
    "detect_temporary_solutions",
    "detect_useless_wrappers",
    "is_test_path",
    "max_nesting_depth",
    "normalize_code_tokens",
    "run_quality_detectors",
    "sort_findings",
    "token_similarity",
]
