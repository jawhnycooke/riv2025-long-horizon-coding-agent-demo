"""Pytest configuration and fixtures for Claude Code Agent tests."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from src.config import DEFAULT_MODEL, ProjectConfig, Provider


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_anthropic_config() -> dict[str, Any]:
    """Sample Anthropic provider configuration."""
    return {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
    }


@pytest.fixture
def sample_bedrock_config() -> dict[str, Any]:
    """Sample Bedrock provider configuration."""
    return {
        "provider": "bedrock",
        "model": "claude-opus-4-5-20251101",
        "bedrock": {
            "region": "us-west-2",
            "profile": "TestProfile",
            "inference_profile": None,
        },
        "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
    }


@pytest.fixture
def config_file(temp_dir: Path, sample_bedrock_config: dict[str, Any]) -> Path:
    """Create a temporary .claude-code.json config file."""
    config_path = temp_dir / ".claude-code.json"
    with open(config_path, "w") as f:
        json.dump(sample_bedrock_config, f)
    return config_path


@pytest.fixture
def project_config_anthropic() -> ProjectConfig:
    """Create an Anthropic ProjectConfig instance."""
    return ProjectConfig(
        provider=Provider.ANTHROPIC,
        model="claude-sonnet-4-5-20250929",
        anthropic_api_key_env_var="ANTHROPIC_API_KEY",
    )


@pytest.fixture
def project_config_bedrock() -> ProjectConfig:
    """Create a Bedrock ProjectConfig instance."""
    return ProjectConfig(
        provider=Provider.BEDROCK,
        model=DEFAULT_MODEL,
        bedrock_region="us-east-1",
        bedrock_profile="ClaudeCode",
    )


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Temporarily clear relevant environment variables."""
    env_vars = [
        "CLAUDE_CODE_USE_BEDROCK",
        "AWS_REGION",
        "AWS_PROFILE",
        "ANTHROPIC_API_KEY",
    ]
    original = {k: os.environ.get(k) for k in env_vars}

    # Clear variables
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def mock_anthropic_key() -> Generator[None, None, None]:
    """Set a mock Anthropic API key."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "test-api-key-12345"
    yield
    if original is not None:
        os.environ["ANTHROPIC_API_KEY"] = original
    elif "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]


# ============================================================================
# Security Test Fixtures
# ============================================================================


@pytest.fixture
def project_root(temp_dir: Path) -> Path:
    """Create a mock project root with common directories."""
    # Create typical project structure
    (temp_dir / "src").mkdir()
    (temp_dir / "tests").mkdir()
    (temp_dir / "screenshots").mkdir()
    (temp_dir / "generated-app").mkdir()
    return temp_dir


@pytest.fixture
def mock_input_data() -> dict[str, Any]:
    """Sample input data for security hook testing."""
    return {"command": "ls -la", "file_path": "/test/path"}


# ============================================================================
# Git Fixtures
# ============================================================================


@pytest.fixture
def mock_git_repo(temp_dir: Path) -> Path:
    """Create a mock git repository."""
    git_dir = temp_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config").touch()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    return temp_dir


@pytest.fixture
def mock_subprocess() -> Generator[MagicMock, None, None]:
    """Mock subprocess.run for git command testing."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="success", stderr=""
        )
        yield mock_run


# ============================================================================
# AWS/Boto3 Fixtures
# ============================================================================


@pytest.fixture
def mock_boto3_session() -> Generator[MagicMock, None, None]:
    """Mock boto3.Session for AWS credential testing."""
    with patch("boto3.Session") as mock_session:
        mock_instance = MagicMock()
        mock_instance.client.return_value = MagicMock()
        mock_session.return_value = mock_instance
        yield mock_session


@pytest.fixture
def mock_sts_client() -> Generator[MagicMock, None, None]:
    """Mock STS client for credential validation."""
    with patch("boto3.client") as mock_client:
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
        }
        mock_client.return_value = mock_sts
        yield mock_client
