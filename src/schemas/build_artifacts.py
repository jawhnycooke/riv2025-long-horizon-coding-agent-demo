"""Build artifacts schema for deployment metadata.

This schema defines the format for build artifact manifests,
used when a build session completes to document what was created.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json


# JSON Schema for build artifacts (compatible with SDK output_format)
BUILD_ARTIFACTS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "BuildArtifacts",
    "description": "Manifest of files and metadata from a completed build",
    "required": ["files", "metadata"],
    "properties": {
        "files": {
            "type": "array",
            "description": "List of files in the build",
            "items": {
                "type": "object",
                "required": ["path", "type"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "source",
                            "config",
                            "test",
                            "asset",
                            "documentation",
                            "generated",
                        ],
                        "description": "File type category",
                    },
                    "size_bytes": {
                        "type": "integer",
                        "description": "File size in bytes",
                    },
                    "checksum": {
                        "type": "string",
                        "description": "SHA256 checksum of the file",
                    },
                    "created": {
                        "type": "boolean",
                        "description": "True if file was created (vs modified)",
                    },
                },
            },
        },
        "metadata": {
            "type": "object",
            "description": "Build metadata",
            "required": ["build_time", "project_name"],
            "properties": {
                "build_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp of build completion",
                },
                "project_name": {
                    "type": "string",
                    "description": "Name of the project",
                },
                "build_plan_version": {
                    "type": "string",
                    "description": "Version of BUILD_PLAN.md used",
                },
                "total_files": {
                    "type": "integer",
                    "description": "Total number of files in build",
                },
                "total_size_bytes": {
                    "type": "integer",
                    "description": "Total size of all files in bytes",
                },
                "tests_passed": {
                    "type": "integer",
                    "description": "Number of tests passing",
                },
                "tests_total": {
                    "type": "integer",
                    "description": "Total number of tests",
                },
                "git_commit": {
                    "type": "string",
                    "description": "Git commit SHA of the build",
                },
                "git_branch": {
                    "type": "string",
                    "description": "Git branch name",
                },
            },
        },
        "deployment_config": {
            "type": "object",
            "description": "Deployment configuration",
            "properties": {
                "entry_point": {
                    "type": "string",
                    "description": "Main entry point file (e.g., index.html)",
                },
                "build_command": {
                    "type": "string",
                    "description": "Command to build for production",
                },
                "output_directory": {
                    "type": "string",
                    "description": "Directory containing built assets",
                },
                "environment_variables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required environment variables (names only)",
                },
                "node_version": {
                    "type": "string",
                    "description": "Required Node.js version",
                },
            },
        },
        "screenshots": {
            "type": "array",
            "description": "Verification screenshots",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "test_id": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
    },
    "additionalProperties": False,
}


@dataclass
class BuildFile:
    """A file in the build."""

    path: str
    type: str  # "source", "config", "test", "asset", "documentation", "generated"
    size_bytes: int = 0
    checksum: str | None = None
    created: bool = True

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": self.path,
            "type": self.type,
        }
        if self.size_bytes:
            result["size_bytes"] = self.size_bytes
        if self.checksum:
            result["checksum"] = self.checksum
        result["created"] = self.created
        return result


@dataclass
class BuildMetadata:
    """Build metadata."""

    build_time: str
    project_name: str
    build_plan_version: str | None = None
    total_files: int = 0
    total_size_bytes: int = 0
    tests_passed: int = 0
    tests_total: int = 0
    git_commit: str | None = None
    git_branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "build_time": self.build_time,
            "project_name": self.project_name,
        }
        if self.build_plan_version:
            result["build_plan_version"] = self.build_plan_version
        result["total_files"] = self.total_files
        result["total_size_bytes"] = self.total_size_bytes
        result["tests_passed"] = self.tests_passed
        result["tests_total"] = self.tests_total
        if self.git_commit:
            result["git_commit"] = self.git_commit
        if self.git_branch:
            result["git_branch"] = self.git_branch
        return result


@dataclass
class DeploymentConfig:
    """Deployment configuration."""

    entry_point: str = "index.html"
    build_command: str = "npm run build"
    output_directory: str = "dist"
    environment_variables: list[str] = field(default_factory=list)
    node_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "entry_point": self.entry_point,
            "build_command": self.build_command,
            "output_directory": self.output_directory,
        }
        if self.environment_variables:
            result["environment_variables"] = self.environment_variables
        if self.node_version:
            result["node_version"] = self.node_version
        return result


@dataclass
class Screenshot:
    """A verification screenshot."""

    path: str
    test_id: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"path": self.path}
        if self.test_id:
            result["test_id"] = self.test_id
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class BuildArtifacts:
    """Complete build artifacts manifest."""

    files: list[BuildFile]
    metadata: BuildMetadata
    deployment_config: DeploymentConfig | None = None
    screenshots: list[Screenshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "files": [f.to_dict() for f in self.files],
            "metadata": self.metadata.to_dict(),
        }
        if self.deployment_config:
            result["deployment_config"] = self.deployment_config.to_dict()
        if self.screenshots:
            result["screenshots"] = [s.to_dict() for s in self.screenshots]
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def create_manifest(
        cls,
        project_name: str,
        files: list[BuildFile],
        tests_passed: int = 0,
        tests_total: int = 0,
        git_commit: str | None = None,
        git_branch: str | None = None,
        build_plan_version: str | None = None,
    ) -> "BuildArtifacts":
        """Factory method to create a build manifest.

        Args:
            project_name: Name of the project
            files: List of BuildFile objects
            tests_passed: Number of tests passing
            tests_total: Total number of tests
            git_commit: Current git commit SHA
            git_branch: Current git branch
            build_plan_version: Version from BUILD_PLAN.md

        Returns:
            BuildArtifacts instance
        """
        total_size = sum(f.size_bytes for f in files)

        metadata = BuildMetadata(
            build_time=datetime.utcnow().isoformat() + "Z",
            project_name=project_name,
            build_plan_version=build_plan_version,
            total_files=len(files),
            total_size_bytes=total_size,
            tests_passed=tests_passed,
            tests_total=tests_total,
            git_commit=git_commit,
            git_branch=git_branch,
        )

        deployment_config = DeploymentConfig()

        return cls(
            files=files,
            metadata=metadata,
            deployment_config=deployment_config,
        )


def validate_build_artifacts(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate build artifacts against the schema.

    Args:
        data: Dictionary to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []

    # Check required fields
    required = ["files", "metadata"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate files array
    if "files" in data:
        if not isinstance(data["files"], list):
            errors.append("Field 'files' must be an array")
        else:
            valid_types = [
                "source",
                "config",
                "test",
                "asset",
                "documentation",
                "generated",
            ]
            for i, file in enumerate(data["files"]):
                if not isinstance(file, dict):
                    errors.append(f"files[{i}] must be an object")
                    continue
                if "path" not in file:
                    errors.append(f"files[{i}] missing required field: path")
                if "type" not in file:
                    errors.append(f"files[{i}] missing required field: type")
                elif file["type"] not in valid_types:
                    errors.append(
                        f"files[{i}].type must be one of: {valid_types}"
                    )

    # Validate metadata
    if "metadata" in data:
        if not isinstance(data["metadata"], dict):
            errors.append("Field 'metadata' must be an object")
        else:
            metadata = data["metadata"]
            if "build_time" not in metadata:
                errors.append("metadata missing required field: build_time")
            if "project_name" not in metadata:
                errors.append("metadata missing required field: project_name")

    return len(errors) == 0, errors
