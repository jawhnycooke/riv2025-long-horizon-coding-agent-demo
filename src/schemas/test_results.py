"""Test results schema for structured test output.

This schema defines the format for test execution results,
used by the Worker agent when reporting test outcomes.
"""

from dataclasses import dataclass, field
from typing import Any
import json


# JSON Schema for test results (compatible with SDK output_format)
TEST_RESULTS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "TestResults",
    "description": "Structured output for test execution results",
    "required": ["passed", "tests", "summary"],
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "True if all tests passed, false otherwise",
        },
        "tests": {
            "type": "array",
            "description": "Individual test results",
            "items": {
                "type": "object",
                "required": ["name", "status"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Test name or ID from tests.json",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["passed", "failed", "skipped", "pending"],
                        "description": "Test execution status",
                    },
                    "screenshot": {
                        "type": "string",
                        "description": "Path to verification screenshot (if taken)",
                    },
                    "console_log": {
                        "type": "string",
                        "description": "Path to console output log (if captured)",
                    },
                    "error": {
                        "type": "string",
                        "description": "Error message (if test failed)",
                    },
                    "duration_ms": {
                        "type": "number",
                        "description": "Test duration in milliseconds",
                    },
                },
            },
        },
        "summary": {
            "type": "string",
            "description": "Human-readable summary of test results",
        },
        "total_passed": {
            "type": "integer",
            "description": "Number of tests that passed",
        },
        "total_failed": {
            "type": "integer",
            "description": "Number of tests that failed",
        },
        "total_skipped": {
            "type": "integer",
            "description": "Number of tests that were skipped",
        },
        "execution_time_ms": {
            "type": "number",
            "description": "Total test execution time in milliseconds",
        },
    },
    "additionalProperties": False,
}


@dataclass
class TestResultItem:
    """Individual test result."""

    name: str
    status: str  # "passed", "failed", "skipped", "pending"
    screenshot: str | None = None
    console_log: str | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
        }
        if self.screenshot:
            result["screenshot"] = self.screenshot
        if self.console_log:
            result["console_log"] = self.console_log
        if self.error:
            result["error"] = self.error
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result


@dataclass
class TestResult:
    """Complete test execution result."""

    passed: bool
    tests: list[TestResultItem]
    summary: str
    total_passed: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    execution_time_ms: float = 0.0

    def __post_init__(self) -> None:
        """Calculate totals if not provided."""
        if self.total_passed == 0 and self.total_failed == 0:
            self.total_passed = sum(1 for t in self.tests if t.status == "passed")
            self.total_failed = sum(1 for t in self.tests if t.status == "failed")
            self.total_skipped = sum(1 for t in self.tests if t.status == "skipped")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "tests": [t.to_dict() for t in self.tests],
            "summary": self.summary,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_skipped": self.total_skipped,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResult":
        """Create TestResult from dictionary."""
        tests = [
            TestResultItem(
                name=t["name"],
                status=t["status"],
                screenshot=t.get("screenshot"),
                console_log=t.get("console_log"),
                error=t.get("error"),
                duration_ms=t.get("duration_ms"),
            )
            for t in data.get("tests", [])
        ]
        return cls(
            passed=data["passed"],
            tests=tests,
            summary=data["summary"],
            total_passed=data.get("total_passed", 0),
            total_failed=data.get("total_failed", 0),
            total_skipped=data.get("total_skipped", 0),
            execution_time_ms=data.get("execution_time_ms", 0.0),
        )


def validate_test_results(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate test results against the schema.

    Args:
        data: Dictionary to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []

    # Check required fields
    required = ["passed", "tests", "summary"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate passed field
    if "passed" in data and not isinstance(data["passed"], bool):
        errors.append("Field 'passed' must be a boolean")

    # Validate tests array
    if "tests" in data:
        if not isinstance(data["tests"], list):
            errors.append("Field 'tests' must be an array")
        else:
            for i, test in enumerate(data["tests"]):
                if not isinstance(test, dict):
                    errors.append(f"tests[{i}] must be an object")
                    continue
                if "name" not in test:
                    errors.append(f"tests[{i}] missing required field: name")
                if "status" not in test:
                    errors.append(f"tests[{i}] missing required field: status")
                elif test["status"] not in ["passed", "failed", "skipped", "pending"]:
                    errors.append(
                        f"tests[{i}].status must be one of: passed, failed, skipped, pending"
                    )

    # Validate summary
    if "summary" in data and not isinstance(data["summary"], str):
        errors.append("Field 'summary' must be a string")

    return len(errors) == 0, errors
