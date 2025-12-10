#!/usr/bin/env python3
"""
Structured Outputs Example

Demonstrates how to use JSON schema validation for agent outputs
using the Claude Agent SDK.

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python examples/structured-outputs.py
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


# =============================================================================
# JSON Schemas
# =============================================================================


TEST_RESULTS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "Whether all tests passed",
        },
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"enum": ["passed", "failed", "skipped"]},
                    "screenshot": {"type": ["string", "null"]},
                    "error": {"type": ["string", "null"]},
                    "duration_ms": {"type": "number"},
                },
                "required": ["name", "status"],
            },
        },
        "summary": {
            "type": "string",
            "description": "Human-readable summary of results",
        },
        "total_duration_ms": {"type": "number"},
    },
    "required": ["passed", "tests", "summary"],
}


PROGRESS_REPORT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "phase": {
            "type": "string",
            "enum": ["initialization", "implementation", "verification", "cleanup"],
        },
        "completed_tasks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "remaining_tasks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
        },
        "metrics": {
            "type": "object",
            "properties": {
                "tokens_used": {"type": "integer"},
                "duration_seconds": {"type": "number"},
                "files_modified": {"type": "integer"},
                "tests_passed": {"type": "integer"},
                "tests_failed": {"type": "integer"},
            },
        },
    },
    "required": ["phase", "completed_tasks", "remaining_tasks"],
}


BUILD_ARTIFACTS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "type": {"enum": ["source", "config", "test", "asset", "documentation"]},
                    "size_bytes": {"type": "integer"},
                    "checksum": {"type": "string"},
                },
                "required": ["path", "type"],
            },
        },
        "metadata": {
            "type": "object",
            "properties": {
                "build_id": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "version": {"type": "string"},
                "git_commit": {"type": "string"},
            },
        },
        "deployment_config": {
            "type": "object",
            "properties": {
                "target": {"enum": ["development", "staging", "production"]},
                "url": {"type": "string"},
                "environment_vars": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    },
    "required": ["files", "metadata"],
}


# =============================================================================
# Python Dataclasses (Type-Safe)
# =============================================================================


@dataclass
class TestResult:
    """Individual test result."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    screenshot: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class TestResults:
    """Collection of test results."""

    passed: bool
    tests: list[TestResult]
    summary: str
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "tests": [asdict(t) for t in self.tests],
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResults":
        """Create from dictionary."""
        tests = [TestResult(**t) for t in data.get("tests", [])]
        return cls(
            passed=data["passed"],
            tests=tests,
            summary=data["summary"],
            total_duration_ms=data.get("total_duration_ms", 0.0),
        )


@dataclass
class Metrics:
    """Session metrics."""

    tokens_used: int = 0
    duration_seconds: float = 0.0
    files_modified: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


@dataclass
class ProgressReport:
    """Session progress report."""

    phase: Literal["initialization", "implementation", "verification", "cleanup"]
    completed_tasks: list[str] = field(default_factory=list)
    remaining_tasks: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "phase": self.phase,
            "completed_tasks": self.completed_tasks,
            "remaining_tasks": self.remaining_tasks,
            "blockers": self.blockers,
            "metrics": asdict(self.metrics),
        }


@dataclass
class FileArtifact:
    """Build file artifact."""

    path: str
    type: Literal["source", "config", "test", "asset", "documentation"]
    size_bytes: int = 0
    checksum: str = ""


@dataclass
class BuildMetadata:
    """Build metadata."""

    build_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "0.0.0"
    git_commit: str = ""


@dataclass
class DeploymentConfig:
    """Deployment configuration."""

    target: Literal["development", "staging", "production"]
    url: str = ""
    environment_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildArtifacts:
    """Complete build artifacts."""

    files: list[FileArtifact]
    metadata: BuildMetadata
    deployment_config: DeploymentConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "files": [asdict(f) for f in self.files],
            "metadata": asdict(self.metadata),
        }
        if self.deployment_config:
            result["deployment_config"] = asdict(self.deployment_config)
        return result


# =============================================================================
# Example Usage
# =============================================================================


def main() -> None:
    """Demonstrate structured outputs."""
    import json

    print("Structured Output Schemas")
    print("=" * 50)

    # Example: Test Results
    print("\n1. Test Results Schema")
    print("-" * 30)

    test_results = TestResults(
        passed=True,
        tests=[
            TestResult(
                name="Homepage renders",
                status="passed",
                screenshot="screenshots/T001.png",
                duration_ms=1234.5,
            ),
            TestResult(
                name="Login form works",
                status="passed",
                screenshot="screenshots/T002.png",
                duration_ms=2345.6,
            ),
            TestResult(
                name="API error handling",
                status="failed",
                error="Expected 404, got 500",
                duration_ms=567.8,
            ),
        ],
        summary="2 of 3 tests passed",
        total_duration_ms=4147.9,
    )

    print("Example TestResults:")
    print(json.dumps(test_results.to_dict(), indent=2))

    # Example: Progress Report
    print("\n2. Progress Report Schema")
    print("-" * 30)

    progress = ProgressReport(
        phase="implementation",
        completed_tasks=[
            "Set up project structure",
            "Implement homepage",
            "Add navigation",
        ],
        remaining_tasks=[
            "Implement user profile",
            "Add settings page",
            "Write tests",
        ],
        blockers=["Waiting for API documentation"],
        metrics=Metrics(
            tokens_used=150000,
            duration_seconds=3600.0,
            files_modified=12,
            tests_passed=2,
            tests_failed=1,
        ),
    )

    print("Example ProgressReport:")
    print(json.dumps(progress.to_dict(), indent=2))

    # Example: Build Artifacts
    print("\n3. Build Artifacts Schema")
    print("-" * 30)

    artifacts = BuildArtifacts(
        files=[
            FileArtifact(
                path="src/App.tsx",
                type="source",
                size_bytes=2048,
                checksum="abc123",
            ),
            FileArtifact(
                path="package.json",
                type="config",
                size_bytes=512,
                checksum="def456",
            ),
            FileArtifact(
                path="tests/App.test.tsx",
                type="test",
                size_bytes=1024,
                checksum="ghi789",
            ),
        ],
        metadata=BuildMetadata(
            build_id="build-001",
            version="1.0.0",
            git_commit="abc123def",
        ),
        deployment_config=DeploymentConfig(
            target="staging",
            url="https://staging.example.com",
            environment_vars={"NODE_ENV": "staging"},
        ),
    )

    print("Example BuildArtifacts:")
    print(json.dumps(artifacts.to_dict(), indent=2))

    print("\n" + "=" * 50)
    print("SDK Integration")
    print("=" * 50)
    print(
        """
To use structured outputs with the Claude SDK:

```python
from claude_sdk import ClaudeSDKClient, ClaudeAgentOptions

client = ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-sonnet-4-20250514",
        system_prompt=SYSTEM_PROMPT,
        output_format={
            "type": "json_schema",
            "schema": TEST_RESULTS_SCHEMA,
        },
        # ... other options
    )
)

# Agent output will be validated against schema
result = await client.run(prompt)
test_results = TestResults.from_dict(result.output)
```

Benefits:
1. Type safety - Outputs match expected structure
2. Validation - Invalid outputs are rejected
3. Parsing - Easy to convert to Python objects
4. Documentation - Schema serves as contract
"""
    )


if __name__ == "__main__":
    main()
