"""Progress report schema for session handoff.

This schema defines the format for progress reports that enable
clean session handoff between agent sessions, as recommended in
Anthropic's "Effective Harnesses for Long-Running Agents" article.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json


# JSON Schema for progress reports (compatible with SDK output_format)
PROGRESS_REPORT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "ProgressReport",
    "description": "Structured output for session progress and handoff",
    "required": ["phase", "completed_tasks", "remaining_tasks"],
    "properties": {
        "session_id": {
            "type": "string",
            "description": "Unique identifier for this session",
        },
        "phase": {
            "type": "string",
            "enum": [
                "initialization",
                "exploration",
                "implementation",
                "testing",
                "verification",
                "cleanup",
                "complete",
            ],
            "description": "Current phase of development",
        },
        "build_plan_version": {
            "type": "string",
            "description": "Version of BUILD_PLAN.md being used",
        },
        "completed_tasks": {
            "type": "array",
            "description": "Tasks completed in this session",
            "items": {
                "type": "object",
                "required": ["task", "status"],
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["done", "partial"],
                        "description": "Completion status",
                    },
                    "test_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Related test IDs from tests.json",
                    },
                    "files_modified": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files modified for this task",
                    },
                },
            },
        },
        "remaining_tasks": {
            "type": "array",
            "description": "Tasks still to be completed",
            "items": {
                "type": "object",
                "required": ["task", "priority"],
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Task priority",
                    },
                    "estimated_complexity": {
                        "type": "string",
                        "enum": ["simple", "moderate", "complex"],
                        "description": "Estimated implementation complexity",
                    },
                },
            },
        },
        "blockers": {
            "type": "array",
            "description": "Issues blocking progress",
            "items": {
                "type": "object",
                "required": ["description"],
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Blocker description",
                    },
                    "file_line": {
                        "type": "string",
                        "description": "File and line reference (e.g., 'src/app.tsx:42')",
                    },
                    "suggested_fix": {
                        "type": "string",
                        "description": "Suggested approach to resolve",
                    },
                },
            },
        },
        "next_actions": {
            "type": "array",
            "description": "Recommended next actions for the following session",
            "items": {"type": "string"},
        },
        "metrics": {
            "type": "object",
            "description": "Session metrics",
            "properties": {
                "tokens_used": {
                    "type": "integer",
                    "description": "Total tokens consumed this session",
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "Session duration in seconds",
                },
                "files_created": {
                    "type": "integer",
                    "description": "Number of new files created",
                },
                "files_modified": {
                    "type": "integer",
                    "description": "Number of existing files modified",
                },
                "tests_passed": {
                    "type": "integer",
                    "description": "Number of tests now passing",
                },
                "tests_total": {
                    "type": "integer",
                    "description": "Total number of tests",
                },
            },
        },
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 timestamp of report generation",
        },
    },
    "additionalProperties": False,
}


@dataclass
class CompletedTask:
    """A completed task."""

    task: str
    status: str = "done"  # "done" or "partial"
    test_ids: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "task": self.task,
            "status": self.status,
        }
        if self.test_ids:
            result["test_ids"] = self.test_ids
        if self.files_modified:
            result["files_modified"] = self.files_modified
        return result


@dataclass
class RemainingTask:
    """A task still to be completed."""

    task: str
    priority: str = "medium"  # "high", "medium", "low"
    estimated_complexity: str = "moderate"  # "simple", "moderate", "complex"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "priority": self.priority,
            "estimated_complexity": self.estimated_complexity,
        }


@dataclass
class Blocker:
    """An issue blocking progress."""

    description: str
    file_line: str | None = None
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"description": self.description}
        if self.file_line:
            result["file_line"] = self.file_line
        if self.suggested_fix:
            result["suggested_fix"] = self.suggested_fix
        return result


@dataclass
class SessionMetrics:
    """Metrics for the session."""

    tokens_used: int = 0
    duration_seconds: float = 0.0
    files_created: int = 0
    files_modified: int = 0
    tests_passed: int = 0
    tests_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens_used": self.tokens_used,
            "duration_seconds": self.duration_seconds,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
        }


@dataclass
class ProgressReport:
    """Complete progress report for session handoff."""

    phase: str
    completed_tasks: list[CompletedTask]
    remaining_tasks: list[RemainingTask]
    session_id: str | None = None
    build_plan_version: str | None = None
    blockers: list[Blocker] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    metrics: SessionMetrics | None = None
    timestamp: str | None = None

    def __post_init__(self) -> None:
        """Set timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "phase": self.phase,
            "completed_tasks": [t.to_dict() for t in self.completed_tasks],
            "remaining_tasks": [t.to_dict() for t in self.remaining_tasks],
            "timestamp": self.timestamp,
        }
        if self.session_id:
            result["session_id"] = self.session_id
        if self.build_plan_version:
            result["build_plan_version"] = self.build_plan_version
        if self.blockers:
            result["blockers"] = [b.to_dict() for b in self.blockers]
        if self.next_actions:
            result["next_actions"] = self.next_actions
        if self.metrics:
            result["metrics"] = self.metrics.to_dict()
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


def validate_progress_report(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate progress report against the schema.

    Args:
        data: Dictionary to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []

    # Check required fields
    required = ["phase", "completed_tasks", "remaining_tasks"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate phase
    valid_phases = [
        "initialization",
        "exploration",
        "implementation",
        "testing",
        "verification",
        "cleanup",
        "complete",
    ]
    if "phase" in data and data["phase"] not in valid_phases:
        errors.append(f"Invalid phase: {data['phase']}. Must be one of: {valid_phases}")

    # Validate completed_tasks array
    if "completed_tasks" in data:
        if not isinstance(data["completed_tasks"], list):
            errors.append("Field 'completed_tasks' must be an array")

    # Validate remaining_tasks array
    if "remaining_tasks" in data:
        if not isinstance(data["remaining_tasks"], list):
            errors.append("Field 'remaining_tasks' must be an array")

    return len(errors) == 0, errors
