"""Tests for agent.py CLI functionality - argument parsing and validation."""

import argparse
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


# We need to import from agent - handle the module path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import (
    dry_run_simulation,
    parse_arguments,
    validate_config,
)


class TestParseArguments:
    """Tests for the argument parser."""

    def test_dry_run_flag_present(self) -> None:
        """--dry-run flag is recognized by parser."""
        with patch.object(sys, "argv", ["agent.py", "--dry-run"]):
            args = parse_arguments()
            assert args.dry_run is True

    def test_dry_run_default_false(self) -> None:
        """--dry-run defaults to False when not specified."""
        with patch.object(sys, "argv", ["agent.py"]):
            args = parse_arguments()
            assert args.dry_run is False

    def test_dry_run_with_project(self) -> None:
        """--dry-run can be combined with --project."""
        with patch.object(
            sys, "argv", ["agent.py", "--dry-run", "--project", "canopy"]
        ):
            args = parse_arguments()
            assert args.dry_run is True
            assert args.project == "canopy"

    def test_dry_run_with_provider(self) -> None:
        """--dry-run can be combined with --provider."""
        with patch.object(
            sys, "argv", ["agent.py", "--dry-run", "--provider", "anthropic"]
        ):
            args = parse_arguments()
            assert args.dry_run is True
            assert args.provider == "anthropic"

    def test_version_flag(self) -> None:
        """--version flag is recognized."""
        with patch.object(sys, "argv", ["agent.py", "--version"]):
            args = parse_arguments()
            assert args.version is True

    def test_validate_flag(self) -> None:
        """--validate flag is recognized."""
        with patch.object(sys, "argv", ["agent.py", "--validate"]):
            args = parse_arguments()
            assert args.validate is True


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_validate_missing_config_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation fails when .claude-code.json is missing."""
        monkeypatch.chdir(tmp_path)
        # Capture output
        captured = StringIO()
        with patch("sys.stdout", captured):
            result = validate_config()
        assert result is False
        assert "Missing .claude-code.json" in captured.getvalue()

    def test_validate_valid_anthropic_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation passes for valid Anthropic configuration."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        # Set API key
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = validate_config()
        assert result is True
        assert "All validations passed" in captured.getvalue()

    def test_validate_anthropic_missing_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation fails when Anthropic API key is missing."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        # Ensure no API key
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = validate_config()
        assert result is False
        assert "Missing Anthropic API key" in captured.getvalue()

    def test_validate_with_provider_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Provider override changes which credentials are validated."""
        monkeypatch.chdir(tmp_path)
        # Create bedrock config
        config = {
            "provider": "bedrock",
            "model": "claude-sonnet-4-5-20250929",
            "bedrock": {"region": "us-east-1"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        # Set Anthropic key (not Bedrock)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        captured = StringIO()
        with patch("sys.stdout", captured):
            # Override to anthropic should use API key validation
            result = validate_config(provider_override="anthropic")
        assert result is True
        output = captured.getvalue()
        assert "(from --provider)" in output
        assert "Anthropic API key" in output

    def test_validate_project_build_plan_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation checks BUILD_PLAN.md when project is specified."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Create prompts directory with BUILD_PLAN.md
        prompts_dir = tmp_path / "prompts" / "myproject"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "BUILD_PLAN.md").write_text("# My Build Plan")
        (tmp_path / "prompts" / "system_prompt.txt").write_text("System prompt")

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = validate_config(project="myproject")
        assert result is True
        assert "Build plan:" in captured.getvalue()

    def test_validate_project_build_plan_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation fails when BUILD_PLAN.md is missing for project."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Don't create prompts directory

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = validate_config(project="nonexistent")
        assert result is False
        assert "Missing" in captured.getvalue()


class TestDryRunSimulation:
    """Tests for dry_run_simulation function."""

    def test_dry_run_returns_true_on_valid_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry run returns True when configuration is valid."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Create prompts directory
        prompts_dir = tmp_path / "prompts" / "testproject"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "BUILD_PLAN.md").write_text("---\nversion: '1.0.0'\n---\n# Plan")
        (tmp_path / "prompts" / "system_prompt.txt").write_text("System prompt here")

        # Create args namespace
        args = argparse.Namespace(
            project="testproject",
            provider=None,
            model="claude-sonnet-4-5-20250929",
            frontend_port=6174,
            backend_port=4001,
            cleanup_session=False,
            enhance_feature=None,
            start_paused=False,
            output_dir=None,
        )

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = dry_run_simulation(args)
        assert result is True
        output = captured.getvalue()
        assert "DRY RUN MODE" in output
        assert "DRY RUN PASSED" in output
        assert "version 1.0.0" in output

    def test_dry_run_returns_false_on_invalid_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry run returns False when configuration is invalid."""
        monkeypatch.chdir(tmp_path)
        # Don't create config file

        args = argparse.Namespace(
            project=None,
            provider=None,
            model="claude-sonnet-4-5-20250929",
            frontend_port=6174,
            backend_port=4001,
            cleanup_session=False,
            enhance_feature=None,
            start_paused=False,
            output_dir=None,
        )

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = dry_run_simulation(args)
        assert result is False
        assert "Dry run failed" in captured.getvalue()

    def test_dry_run_shows_execution_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry run shows what would be executed."""
        monkeypatch.chdir(tmp_path)
        # Create config file
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Create prompts
        prompts_dir = tmp_path / "prompts" / "demo"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "BUILD_PLAN.md").write_text("# Demo Plan")
        (tmp_path / "prompts" / "system_prompt.txt").write_text("System prompt")

        args = argparse.Namespace(
            project="demo",
            provider=None,
            model="claude-sonnet-4-5-20250929",
            frontend_port=8080,
            backend_port=3000,
            cleanup_session=False,
            enhance_feature=None,
            start_paused=False,
            output_dir=None,
        )

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = dry_run_simulation(args)

        output = captured.getvalue()
        assert result is True
        assert "Execution plan" in output
        assert "Initialize session" in output
        assert "Copy prompts" in output
        assert "Initialize git repository" in output
        assert "Start Claude Agent SDK" in output

    def test_dry_run_with_cleanup_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry run correctly shows cleanup mode when specified."""
        monkeypatch.chdir(tmp_path)
        # Create minimal valid config
        config = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "anthropic": {"api_key_env_var": "ANTHROPIC_API_KEY"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        prompts_dir = tmp_path / "prompts" / "test"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "BUILD_PLAN.md").write_text("# Plan")
        (tmp_path / "prompts" / "system_prompt.txt").write_text("System")

        args = argparse.Namespace(
            project="test",
            provider=None,
            model="claude-sonnet-4-5-20250929",
            frontend_port=6174,
            backend_port=4001,
            cleanup_session=True,  # Cleanup mode enabled
            enhance_feature=None,
            start_paused=False,
            output_dir=None,
        )

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = dry_run_simulation(args)

        output = captured.getvalue()
        assert result is True
        assert "Mode: Cleanup session" in output
        assert "cleanup mode" in output

    def test_dry_run_with_provider_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry run respects provider override from CLI."""
        monkeypatch.chdir(tmp_path)
        # Create bedrock config
        config = {
            "provider": "bedrock",
            "model": "claude-sonnet-4-5-20250929",
            "bedrock": {"region": "us-east-1"},
        }
        (tmp_path / ".claude-code.json").write_text(json.dumps(config))
        # Set Anthropic key (overriding to anthropic)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        prompts_dir = tmp_path / "prompts" / "test"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "BUILD_PLAN.md").write_text("# Plan")
        (tmp_path / "prompts" / "system_prompt.txt").write_text("System")

        args = argparse.Namespace(
            project="test",
            provider="anthropic",  # Override to anthropic
            model="claude-sonnet-4-5-20250929",
            frontend_port=6174,
            backend_port=4001,
            cleanup_session=False,
            enhance_feature=None,
            start_paused=False,
            output_dir=None,
        )

        captured = StringIO()
        with patch("sys.stdout", captured):
            result = dry_run_simulation(args)

        output = captured.getvalue()
        assert result is True
        assert "anthropic (from --provider flag)" in output
