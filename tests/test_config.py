"""Tests for src/config.py - Configuration loading and provider handling."""

import os
from pathlib import Path
from typing import Any

import pytest

from src.config import (
    DEFAULT_BEDROCK_REGION,
    DEFAULT_COMPLETION_SIGNAL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MODEL_DISPLAY_NAMES,
    SUPPORTED_BEDROCK_REGIONS,
    CompletionSignalSettings,
    ProjectConfig,
    Provider,
    apply_provider_config,
    get_boto3_client,
    get_boto3_session,
    get_default_template_vars,
    get_provider_env_vars,
    load_project_config,
)


class TestProvider:
    """Tests for the Provider enum."""

    def test_provider_values(self) -> None:
        """Provider enum has correct string values."""
        assert Provider.ANTHROPIC.value == "anthropic"
        assert Provider.BEDROCK.value == "bedrock"

    def test_provider_is_string_enum(self) -> None:
        """Provider inherits from str and can be compared directly."""
        # str(Enum) returns "EnumName.MEMBER", but value comparison works
        assert Provider.ANTHROPIC == "anthropic"
        assert Provider.BEDROCK == "bedrock"

    def test_provider_from_string(self) -> None:
        """Provider can be created from string value."""
        assert Provider("anthropic") == Provider.ANTHROPIC
        assert Provider("bedrock") == Provider.BEDROCK

    def test_invalid_provider_raises(self) -> None:
        """Invalid provider string raises ValueError."""
        with pytest.raises(ValueError):
            Provider("invalid")


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_from_dict_anthropic(self, sample_anthropic_config: dict[str, Any]) -> None:
        """Create ProjectConfig from Anthropic configuration dict."""
        config = ProjectConfig.from_dict(sample_anthropic_config)

        assert config.provider == Provider.ANTHROPIC
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.anthropic_api_key_env_var == "ANTHROPIC_API_KEY"
        assert config.bedrock_region == DEFAULT_BEDROCK_REGION  # Default applied

    def test_from_dict_bedrock(self, sample_bedrock_config: dict[str, Any]) -> None:
        """Create ProjectConfig from Bedrock configuration dict."""
        config = ProjectConfig.from_dict(sample_bedrock_config)

        assert config.provider == Provider.BEDROCK
        assert config.model == "claude-opus-4-5-20251101"
        assert config.bedrock_region == "us-west-2"
        assert config.bedrock_profile == "TestProfile"
        assert config.bedrock_inference_profile is None

    def test_from_dict_defaults(self) -> None:
        """Empty dict uses all defaults."""
        config = ProjectConfig.from_dict({})

        assert config.provider == DEFAULT_PROVIDER
        assert config.model == DEFAULT_MODEL
        assert config.bedrock_region == DEFAULT_BEDROCK_REGION
        assert config.anthropic_api_key_env_var == "ANTHROPIC_API_KEY"

    def test_from_dict_invalid_provider_uses_default(self) -> None:
        """Invalid provider string falls back to default."""
        config = ProjectConfig.from_dict({"provider": "invalid_provider"})

        assert config.provider == DEFAULT_PROVIDER

    def test_to_dict_anthropic(self, project_config_anthropic: ProjectConfig) -> None:
        """Convert Anthropic config to dictionary."""
        result = project_config_anthropic.to_dict()

        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-sonnet-4-5-20250929"
        assert result["anthropic"]["api_key_env_var"] == "ANTHROPIC_API_KEY"

    def test_to_dict_bedrock(self, project_config_bedrock: ProjectConfig) -> None:
        """Convert Bedrock config to dictionary."""
        result = project_config_bedrock.to_dict()

        assert result["provider"] == "bedrock"
        assert result["model"] == DEFAULT_MODEL
        assert result["bedrock"]["region"] == "us-east-1"
        assert result["bedrock"]["profile"] == "ClaudeCode"

    def test_roundtrip_conversion(self, sample_bedrock_config: dict[str, Any]) -> None:
        """Config survives from_dict -> to_dict roundtrip."""
        config = ProjectConfig.from_dict(sample_bedrock_config)
        result = config.to_dict()

        # Key fields preserved
        assert result["provider"] == sample_bedrock_config["provider"]
        assert result["model"] == sample_bedrock_config["model"]
        assert result["bedrock"]["region"] == sample_bedrock_config["bedrock"]["region"]


class TestLoadProjectConfig:
    """Tests for load_project_config function."""

    def test_load_existing_config(
        self, config_file: Path, sample_bedrock_config: dict[str, Any]
    ) -> None:
        """Load configuration from existing file."""
        config = load_project_config(config_file)

        assert config is not None
        assert config.provider == Provider.BEDROCK
        assert config.model == sample_bedrock_config["model"]

    def test_load_nonexistent_returns_none(self, temp_dir: Path) -> None:
        """Return None when config file doesn't exist."""
        config = load_project_config(temp_dir / "nonexistent.json")

        assert config is None

    def test_load_invalid_json_returns_none(self, temp_dir: Path) -> None:
        """Return None for invalid JSON content."""
        invalid_config = temp_dir / "invalid.json"
        invalid_config.write_text("{ invalid json }")

        config = load_project_config(invalid_config)

        assert config is None

    def test_load_uses_cwd_default(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default path is .claude-code.json in current directory."""
        monkeypatch.chdir(temp_dir)

        # No config file exists
        config = load_project_config()
        assert config is None

        # Create config file
        (temp_dir / ".claude-code.json").write_text(
            '{"provider": "anthropic", "model": "test-model"}'
        )
        config = load_project_config()
        assert config is not None
        assert config.model == "test-model"


class TestGetProviderEnvVars:
    """Tests for get_provider_env_vars function."""

    def test_bedrock_provider_sets_env_vars(
        self, project_config_bedrock: ProjectConfig
    ) -> None:
        """Bedrock provider sets correct environment variables."""
        env_vars = get_provider_env_vars(project_config_bedrock)

        assert env_vars["CLAUDE_CODE_USE_BEDROCK"] == "1"
        assert env_vars["AWS_REGION"] == "us-east-1"

    def test_anthropic_provider_sets_env_vars(
        self, project_config_anthropic: ProjectConfig
    ) -> None:
        """Anthropic provider sets correct environment variables."""
        env_vars = get_provider_env_vars(project_config_anthropic)

        assert env_vars["CLAUDE_CODE_USE_BEDROCK"] == "0"
        assert "AWS_REGION" not in env_vars

    def test_anthropic_with_api_key(self) -> None:
        """Anthropic config with direct API key sets it in env vars."""
        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model=DEFAULT_MODEL,
            anthropic_api_key="sk-ant-test-key",
        )
        env_vars = get_provider_env_vars(config)

        assert env_vars["ANTHROPIC_API_KEY"] == "sk-ant-test-key"


class TestApplyProviderConfig:
    """Tests for apply_provider_config function."""

    def test_apply_bedrock_config(
        self, clean_env: None, project_config_bedrock: ProjectConfig
    ) -> None:
        """Applying Bedrock config sets environment variables."""
        apply_provider_config(project_config_bedrock)

        assert os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1"
        assert os.environ.get("AWS_REGION") == "us-east-1"

    def test_apply_anthropic_config(
        self, clean_env: None, project_config_anthropic: ProjectConfig
    ) -> None:
        """Applying Anthropic config disables Bedrock mode."""
        apply_provider_config(project_config_anthropic)

        assert os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "0"


class TestConstants:
    """Tests for configuration constants."""

    def test_default_model_is_valid(self) -> None:
        """Default model is a valid Anthropic model ID."""
        from src.config import ANTHROPIC_MODEL_IDS

        assert DEFAULT_MODEL in ANTHROPIC_MODEL_IDS.values()

    def test_default_provider_is_anthropic(self) -> None:
        """Default provider is Anthropic."""
        assert DEFAULT_PROVIDER == Provider.ANTHROPIC

    def test_supported_bedrock_regions(self) -> None:
        """All supported Bedrock regions are valid AWS regions."""
        for region in SUPPORTED_BEDROCK_REGIONS:
            assert (
                region.startswith("us-")
                or region.startswith("eu-")
                or region.startswith("ap-")
            )

    def test_default_bedrock_region_is_supported(self) -> None:
        """Default Bedrock region is in supported list."""
        assert DEFAULT_BEDROCK_REGION in SUPPORTED_BEDROCK_REGIONS


class TestTemplateVars:
    """Tests for template variable functions."""

    def test_get_default_template_vars(self) -> None:
        """Default template variables include ports."""
        vars = get_default_template_vars()

        assert "frontend_port" in vars
        assert "backend_port" in vars
        assert isinstance(vars["frontend_port"], int)
        assert isinstance(vars["backend_port"], int)


class TestBoto3Session:
    """Tests for get_boto3_session and get_boto3_client functions."""

    def test_session_uses_explicit_profile(self, clean_env: None, mocker: Any) -> None:
        """Explicit profile parameter takes priority."""
        import boto3

        mock_session = mocker.MagicMock()
        mock_boto3_session = mocker.patch.object(
            boto3, "Session", return_value=mock_session
        )

        get_boto3_session(profile="test-profile")
        mock_boto3_session.assert_called_once_with(
            profile_name="test-profile", region_name=DEFAULT_BEDROCK_REGION
        )

    def test_session_uses_env_profile(self, clean_env: None, mocker: Any) -> None:
        """AWS_PROFILE environment variable is used when no explicit profile."""
        import boto3

        mock_session = mocker.MagicMock()
        mock_boto3_session = mocker.patch.object(
            boto3, "Session", return_value=mock_session
        )

        os.environ["AWS_PROFILE"] = "env-profile"
        get_boto3_session()
        mock_boto3_session.assert_called_once_with(
            profile_name="env-profile", region_name=DEFAULT_BEDROCK_REGION
        )

    def test_session_explicit_overrides_env_profile(
        self, clean_env: None, mocker: Any
    ) -> None:
        """Explicit profile overrides AWS_PROFILE env var."""
        import boto3

        mock_session = mocker.MagicMock()
        mock_boto3_session = mocker.patch.object(
            boto3, "Session", return_value=mock_session
        )

        os.environ["AWS_PROFILE"] = "env-profile"
        get_boto3_session(profile="explicit-profile")
        mock_boto3_session.assert_called_once_with(
            profile_name="explicit-profile", region_name=DEFAULT_BEDROCK_REGION
        )

    def test_session_uses_explicit_region(self, clean_env: None) -> None:
        """Explicit region parameter takes priority."""
        session = get_boto3_session(region="us-west-2")
        assert session.region_name == "us-west-2"

    def test_session_uses_env_region(self, clean_env: None) -> None:
        """AWS_REGION environment variable is used when no explicit region."""
        os.environ["AWS_REGION"] = "eu-west-1"
        session = get_boto3_session()
        assert session.region_name == "eu-west-1"

    def test_session_explicit_overrides_env_region(self, clean_env: None) -> None:
        """Explicit region overrides AWS_REGION env var."""
        os.environ["AWS_REGION"] = "eu-west-1"
        session = get_boto3_session(region="ap-northeast-1")
        assert session.region_name == "ap-northeast-1"

    def test_session_uses_default_region(self, clean_env: None) -> None:
        """Default region is used when nothing specified."""
        session = get_boto3_session()
        assert session.region_name == DEFAULT_BEDROCK_REGION

    def test_client_returns_boto3_client(self, clean_env: None) -> None:
        """get_boto3_client returns a valid boto3 client object."""
        client = get_boto3_client("sts")
        # Verify it's a boto3 client by checking for common client attributes
        assert hasattr(client, "meta")
        assert client.meta.service_model.service_name == "sts"

    def test_client_uses_profile_and_region(self, clean_env: None, mocker: Any) -> None:
        """get_boto3_client passes profile and region to session."""
        import boto3

        mock_client = mocker.MagicMock()
        mock_session = mocker.MagicMock()
        mock_session.client.return_value = mock_client
        mock_boto3_session = mocker.patch.object(
            boto3, "Session", return_value=mock_session
        )

        os.environ["AWS_PROFILE"] = "should-not-use"
        get_boto3_client("sts", profile="test-profile", region="us-west-2")

        mock_boto3_session.assert_called_once_with(
            profile_name="test-profile", region_name="us-west-2"
        )
        # Client is called with service name and optional config parameter
        mock_session.client.assert_called_once()
        call_args = mock_session.client.call_args
        assert call_args[0][0] == "sts"  # First positional arg is service name


class TestCompletionSignalSettings:
    """Tests for CompletionSignalSettings dataclass."""

    def test_default_values(self) -> None:
        """Default instance uses expected defaults."""
        settings = CompletionSignalSettings()

        assert settings.signal == DEFAULT_COMPLETION_SIGNAL
        assert settings.emoji == "🎉"
        assert settings.complete_phrase == "implementation complete"
        assert settings.finished_phrase == "all tasks finished"

    def test_default_class_method(self) -> None:
        """default() class method returns default settings."""
        settings = CompletionSignalSettings.default()

        assert settings.signal == DEFAULT_COMPLETION_SIGNAL
        assert settings.emoji == "🎉"

    def test_from_dict_empty(self) -> None:
        """Empty dict uses all defaults."""
        settings = CompletionSignalSettings.from_dict({})

        assert settings.signal == DEFAULT_COMPLETION_SIGNAL
        assert settings.emoji == "🎉"
        assert settings.complete_phrase == "implementation complete"
        assert settings.finished_phrase == "all tasks finished"

    def test_from_dict_custom_signal(self) -> None:
        """Custom signal is used and emoji is extracted."""
        data = {"signal": "✅ DONE - task complete - all done"}
        settings = CompletionSignalSettings.from_dict(data)

        assert settings.signal == "✅ DONE - task complete - all done"
        assert settings.emoji == "✅"  # Extracted from signal

    def test_from_dict_explicit_components(self) -> None:
        """Explicit components override extraction."""
        data = {
            "signal": "🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED",
            "emoji": "🚀",
            "complete_phrase": "done building",
            "finished_phrase": "all work complete",
        }
        settings = CompletionSignalSettings.from_dict(data)

        assert settings.emoji == "🚀"
        assert settings.complete_phrase == "done building"
        assert settings.finished_phrase == "all work complete"

    def test_from_dict_signal_without_emoji(self) -> None:
        """Signal without emoji uses default emoji."""
        data = {"signal": "DONE - implementation complete - all tasks finished"}
        settings = CompletionSignalSettings.from_dict(data)

        assert settings.signal == "DONE - implementation complete - all tasks finished"
        assert settings.emoji == "🎉"  # Falls back to default

    def test_from_dict_extracts_first_emoji(self) -> None:
        """Extracts first emoji from signal with multiple emojis."""
        data = {"signal": "🎯 Target hit 🎉 Celebration!"}
        settings = CompletionSignalSettings.from_dict(data)

        assert settings.emoji == "🎯"  # First emoji extracted

    def test_to_dict_defaults(self) -> None:
        """to_dict only includes signal when defaults used."""
        settings = CompletionSignalSettings()
        result = settings.to_dict()

        assert result == {"signal": DEFAULT_COMPLETION_SIGNAL}
        assert "emoji" not in result
        assert "complete_phrase" not in result
        assert "finished_phrase" not in result

    def test_to_dict_custom_values(self) -> None:
        """to_dict includes non-default values."""
        settings = CompletionSignalSettings(
            signal="Custom signal",
            emoji="🚀",
            complete_phrase="custom complete",
            finished_phrase="custom finished",
        )
        result = settings.to_dict()

        assert result["signal"] == "Custom signal"
        assert result["emoji"] == "🚀"
        assert result["complete_phrase"] == "custom complete"
        assert result["finished_phrase"] == "custom finished"

    def test_roundtrip_conversion(self) -> None:
        """Settings survive from_dict -> to_dict roundtrip."""
        original_data = {
            "signal": "✅ BUILD COMPLETE - ALL TESTS PASSED",
            "emoji": "✅",
            "complete_phrase": "build complete",
            "finished_phrase": "all tests passed",
        }
        settings = CompletionSignalSettings.from_dict(original_data)
        result = settings.to_dict()

        assert result["signal"] == original_data["signal"]
        assert result["emoji"] == original_data["emoji"]
        assert result["complete_phrase"] == original_data["complete_phrase"]
        assert result["finished_phrase"] == original_data["finished_phrase"]


class TestProjectConfigCompletionSignal:
    """Tests for ProjectConfig integration with CompletionSignalSettings."""

    def test_from_dict_without_completion_signal(self) -> None:
        """Config without completion_signal has None."""
        config = ProjectConfig.from_dict({})

        assert config.completion_signal is None

    def test_from_dict_with_completion_signal(self) -> None:
        """Config with completion_signal parses settings."""
        data = {
            "completion_signal": {
                "signal": "🚀 LAUNCH COMPLETE",
            }
        }
        config = ProjectConfig.from_dict(data)

        assert config.completion_signal is not None
        assert config.completion_signal.signal == "🚀 LAUNCH COMPLETE"
        assert config.completion_signal.emoji == "🚀"

    def test_to_dict_without_completion_signal(self) -> None:
        """to_dict excludes completion_signal when None."""
        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model=DEFAULT_MODEL,
        )
        result = config.to_dict()

        assert "completion_signal" not in result

    def test_to_dict_with_completion_signal(self) -> None:
        """to_dict includes completion_signal when set."""
        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model=DEFAULT_MODEL,
            completion_signal=CompletionSignalSettings(
                signal="✅ COMPLETE",
                emoji="✅",
            ),
        )
        result = config.to_dict()

        assert "completion_signal" in result
        assert result["completion_signal"]["signal"] == "✅ COMPLETE"

    def test_config_roundtrip_with_completion_signal(self) -> None:
        """Config with completion_signal survives roundtrip."""
        original_data = {
            "provider": "anthropic",
            "model": DEFAULT_MODEL,
            "completion_signal": {
                "signal": "🎯 TARGET HIT - all objectives achieved",
                "emoji": "🎯",
                "complete_phrase": "target hit",
                "finished_phrase": "all objectives achieved",
            },
        }
        config = ProjectConfig.from_dict(original_data)
        result = config.to_dict()

        assert (
            result["completion_signal"]["signal"]
            == original_data["completion_signal"]["signal"]
        )
        assert (
            result["completion_signal"]["emoji"]
            == original_data["completion_signal"]["emoji"]
        )
