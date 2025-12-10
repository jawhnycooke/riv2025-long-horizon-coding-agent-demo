"""JSON schemas for structured agent outputs.

This module defines JSON schemas that standardize agent outputs,
enabling consistent parsing and validation of:
- Test results (from Worker after test execution)
- Progress reports (from Orchestrator for session handoff)
- Build artifacts (final build metadata)

These schemas can be used with the SDK's output_format parameter
to enforce structured responses.
"""

from src.schemas.test_results import (
    TEST_RESULTS_SCHEMA,
    TestResult,
    TestResultItem,
    validate_test_results,
)
from src.schemas.progress_report import (
    PROGRESS_REPORT_SCHEMA,
    ProgressReport,
    validate_progress_report,
)
from src.schemas.build_artifacts import (
    BUILD_ARTIFACTS_SCHEMA,
    BuildArtifacts,
    BuildFile,
    validate_build_artifacts,
)

__all__ = [
    # Test Results
    "TEST_RESULTS_SCHEMA",
    "TestResult",
    "TestResultItem",
    "validate_test_results",
    # Progress Report
    "PROGRESS_REPORT_SCHEMA",
    "ProgressReport",
    "validate_progress_report",
    # Build Artifacts
    "BUILD_ARTIFACTS_SCHEMA",
    "BuildArtifacts",
    "BuildFile",
    "validate_build_artifacts",
]
