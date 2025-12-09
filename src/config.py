"""Configuration constants and settings for Claude Code."""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Provider(str, Enum):
    """Supported model providers."""

    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"


# Model defaults
DEFAULT_MODEL = "claude-opus-4-5-20251101"
DEFAULT_PROVIDER = Provider.ANTHROPIC

# Bedrock region defaults
DEFAULT_BEDROCK_REGION = "us-east-1"
SUPPORTED_BEDROCK_REGIONS = [
    "us-east-1",
    "us-west-2",
    "eu-west-1",
    "ap-northeast-1",
    "ap-southeast-2",
]

# Model ID mappings - Anthropic model IDs are used as canonical IDs
# Bedrock uses the same IDs but requires CLAUDE_CODE_USE_BEDROCK=1 env var
MODEL_DISPLAY_NAMES = {
    "claude-opus-4-5-20251101": "Claude Opus 4.5",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-haiku-4-5-20250927": "Claude Haiku 4.5",
}


@dataclass
class RetrySettings:
    """Retry configuration settings."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RetrySettings":
        """Create RetrySettings from dictionary."""
        return cls(
            max_retries=data.get("max_retries", 3),
            base_delay=data.get("base_delay", 1.0),
            max_delay=data.get("max_delay", 60.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
        }


@dataclass
class TracingSettings:
    """OpenTelemetry tracing configuration settings."""

    enabled: bool = False
    service_name: str = "claude-code-agent"
    exporter: str = "console"  # "console", "otlp", or "none"
    otlp_endpoint: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TracingSettings":
        """Create TracingSettings from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            service_name=data.get("service_name", "claude-code-agent"),
            exporter=data.get("exporter", "console"),
            otlp_endpoint=data.get("otlp_endpoint"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "exporter": self.exporter,
        }
        if self.otlp_endpoint:
            result["otlp_endpoint"] = self.otlp_endpoint
        return result


# Default completion signal
DEFAULT_COMPLETION_SIGNAL = "🎉 IMPLEMENTATION COMPLETE - ALL TASKS FINISHED"


@dataclass
class CompletionSignalSettings:
    """Completion signal configuration settings.

    The completion signal is the message the agent outputs when it has
    finished all tasks. This signal triggers state transitions and
    marks the issue as complete.
    """

    signal: str = DEFAULT_COMPLETION_SIGNAL
    emoji: str = "🎉"
    complete_phrase: str = "implementation complete"
    finished_phrase: str = "all tasks finished"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionSignalSettings":
        """Create CompletionSignalSettings from dictionary.

        If only 'signal' is provided, extracts emoji and phrases from it.
        """
        signal = data.get("signal", DEFAULT_COMPLETION_SIGNAL)

        # Allow explicit override of detection components
        emoji = data.get("emoji")
        complete_phrase = data.get("complete_phrase")
        finished_phrase = data.get("finished_phrase")

        # If not explicitly provided, extract from signal
        if emoji is None:
            # Find first emoji in signal (common emojis)
            for char in signal:
                if ord(char) > 127 and not char.isspace():
                    emoji = char
                    break
            if emoji is None:
                emoji = "🎉"  # Default emoji

        if complete_phrase is None:
            complete_phrase = "implementation complete"

        if finished_phrase is None:
            finished_phrase = "all tasks finished"

        return cls(
            signal=signal,
            emoji=emoji,
            complete_phrase=complete_phrase,
            finished_phrase=finished_phrase,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "signal": self.signal,
        }
        # Only include detection components if they differ from defaults
        if self.emoji != "🎉":
            result["emoji"] = self.emoji
        if self.complete_phrase != "implementation complete":
            result["complete_phrase"] = self.complete_phrase
        if self.finished_phrase != "all tasks finished":
            result["finished_phrase"] = self.finished_phrase
        return result

    @classmethod
    def default(cls) -> "CompletionSignalSettings":
        """Return default completion signal settings."""
        return cls()


@dataclass
class ProjectConfig:
    """Project configuration loaded from .claude-code.json."""

    provider: Provider
    model: str
    bedrock_region: str | None = None
    bedrock_profile: str | None = None
    bedrock_inference_profile: str | None = None
    anthropic_api_key_env_var: str = "ANTHROPIC_API_KEY"
    anthropic_api_key: str | None = None
    retry: RetrySettings | None = None
    tracing: TracingSettings | None = None
    completion_signal: CompletionSignalSettings | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        """Create ProjectConfig from dictionary."""
        provider_str = data.get("provider", DEFAULT_PROVIDER.value)
        try:
            provider = Provider(provider_str)
        except ValueError:
            provider = DEFAULT_PROVIDER

        bedrock_config = data.get("bedrock", {})
        anthropic_config = data.get("anthropic", {})
        retry_config = data.get("retry", {})
        tracing_config = data.get("tracing", {})
        completion_signal_config = data.get("completion_signal", {})

        return cls(
            provider=provider,
            model=data.get("model", DEFAULT_MODEL),
            bedrock_region=bedrock_config.get("region", DEFAULT_BEDROCK_REGION),
            bedrock_profile=bedrock_config.get("profile"),
            bedrock_inference_profile=bedrock_config.get("inference_profile"),
            anthropic_api_key_env_var=anthropic_config.get(
                "api_key_env_var", "ANTHROPIC_API_KEY"
            ),
            anthropic_api_key=anthropic_config.get("api_key"),
            retry=RetrySettings.from_dict(retry_config) if retry_config else None,
            tracing=(
                TracingSettings.from_dict(tracing_config) if tracing_config else None
            ),
            completion_signal=(
                CompletionSignalSettings.from_dict(completion_signal_config)
                if completion_signal_config
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "provider": self.provider.value,
            "model": self.model,
        }

        if self.provider == Provider.BEDROCK or self.bedrock_region:
            result["bedrock"] = {
                "region": self.bedrock_region or DEFAULT_BEDROCK_REGION,
                "profile": self.bedrock_profile,
                "inference_profile": self.bedrock_inference_profile,
            }

        result["anthropic"] = {
            "api_key_env_var": self.anthropic_api_key_env_var,
        }
        if self.anthropic_api_key:
            result["anthropic"]["api_key"] = self.anthropic_api_key

        if self.retry:
            result["retry"] = self.retry.to_dict()

        if self.tracing:
            result["tracing"] = self.tracing.to_dict()

        if self.completion_signal:
            result["completion_signal"] = self.completion_signal.to_dict()

        return result


def load_project_config(config_path: Path | None = None) -> ProjectConfig | None:
    """
    Load project configuration from .claude-code.json.

    Args:
        config_path: Optional path to config file. Defaults to .claude-code.json in cwd.

    Returns:
        ProjectConfig if file exists and is valid, None otherwise.
    """
    if config_path is None:
        config_path = Path.cwd() / ".claude-code.json"

    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            data = json.load(f)
        return ProjectConfig.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to load config from {config_path}: {e}")
        return None


def get_provider_env_vars(config: ProjectConfig) -> dict[str, str]:
    """
    Get environment variables needed for the configured provider.

    Args:
        config: Project configuration

    Returns:
        Dictionary of environment variables to set
    """
    env_vars: dict[str, str] = {}

    if config.provider == Provider.BEDROCK:
        # Enable Bedrock mode in Claude SDK
        env_vars["CLAUDE_CODE_USE_BEDROCK"] = "1"

        # Set AWS region
        if config.bedrock_region:
            env_vars["AWS_REGION"] = config.bedrock_region

    else:  # Anthropic
        # Ensure Bedrock mode is disabled
        env_vars["CLAUDE_CODE_USE_BEDROCK"] = "0"

        # Set API key if provided directly in config
        if config.anthropic_api_key:
            env_vars["ANTHROPIC_API_KEY"] = config.anthropic_api_key

    return env_vars


def apply_provider_config(config: ProjectConfig) -> None:
    """
    Apply provider configuration to environment.

    Args:
        config: Project configuration to apply
    """
    env_vars = get_provider_env_vars(config)
    for key, value in env_vars.items():
        os.environ[key] = value


# Port defaults
DEFAULT_FRONTEND_PORT = 6174
DEFAULT_BACKEND_PORT = 4001

# Usage limits
MAX_OUTPUT_TOKENS = 500_000_000
MAX_API_CALLS = 5_000
MAX_COST_USD = 5_000.0

# Warning thresholds (as percentages)
WARNING_THRESHOLD_HIGH = 90  # Red warning
WARNING_THRESHOLD_MEDIUM = 75  # Yellow notice

# File patterns for templating
TEMPLATE_FILE_EXTENSIONS = {".txt", ".md"}

# Required project files (system_prompt.txt now comes from top-level prompts directory)
REQUIRED_PROJECT_FILES = ["BUILD_PLAN.md"]
OPTIONAL_PROJECT_FILES = ["DEBUGGING_GUIDE.md", "system_prompt.txt"]

# Log file settings
LOG_FILE_PATTERN = "*.json"
LOGS_DIR_NAME = "logs"

# Security: Allowed bash commands
ALLOWED_BASH_COMMANDS = [
    "npm",
    "npx",
    "pnpm",
    "node",
    "curl",
    "mkdir",
    "echo",
    "ls",
    "cat",
    "cd",
    "pwd",
    "touch",
    "lsof",
    "ps",
    "jq",
    "sed",
    "awk",
    "find",
    "git",
    "cp",
    "wc",
    "grep",
    "sleep",
    "kill",
    "tail",
    "sqlite3",
    "netstat",
    "rg",
    "chmod",
    "./init.sh",
    "test",
    "node",
    "which",
    "time",
    "head",
    "pip",
    "pip3",
    "playwright",
    "python3",
    "google-chrome",
]

# Special command patterns
ALLOWED_RM_COMMANDS = ["rm -rf node_modules"]
ALLOWED_NODE_PATTERNS = ["server.js", "server/index.js", "playwright-test.cjs"]
ALLOWED_PKILL_PATTERNS = [
    'pkill -f "node server/index.js"',
    'pkill -f "node server.js"',
    'pkill -f "vite"',
    'pkill -f "chrome"',
]

# Blocked sed patterns - prevent bulk modification of test results
# These regex patterns match sed commands that should be blocked
BLOCKED_SED_PATTERNS = [
    # Block any sed command that modifies "passes" field in tests.json
    r"sed.*passes.*tests\.json",
    r"sed.*tests\.json.*passes",
    # Block bulk true/false replacements in tests.json
    r"sed.*false.*true.*tests\.json",
    r"sed.*true.*false.*tests\.json",
]

# Block any bash command that could modify tests.json
# Agent must use Edit tool with screenshot verification instead
BLOCKED_TESTS_JSON_PATTERNS = [
    r"awk.*tests\.json",
    r"jq.*tests\.json",
    r"python3?\s.*tests\.json",
    r"node\s.*tests\.json",
    r"echo.*>.*tests\.json",
    r"cat.*>.*tests\.json",
    r"printf.*>.*tests\.json",
    r"tee.*tests\.json",
    r">.*tests\.json",  # Any redirection to tests.json
]


def get_default_template_vars() -> dict[str, Any]:
    """Get default template variables."""
    return {
        "frontend_port": DEFAULT_FRONTEND_PORT,
        "backend_port": DEFAULT_BACKEND_PORT,
    }


def get_boto3_session(
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 session with optional profile and region.

    Priority for profile:
    1. Explicit profile parameter
    2. AWS_PROFILE environment variable
    3. None (use default credentials)

    Priority for region:
    1. Explicit region parameter
    2. AWS_REGION environment variable
    3. Default region (us-east-1)

    Args:
        profile: AWS profile name (optional)
        region: AWS region (optional)

    Returns:
        Configured boto3.Session
    """
    import boto3

    # Profile priority: explicit > env var > None
    profile_name = profile or os.environ.get("AWS_PROFILE")

    # Region priority: explicit > env var > default
    region_name = region or os.environ.get("AWS_REGION", DEFAULT_BEDROCK_REGION)

    return boto3.Session(profile_name=profile_name, region_name=region_name)


def get_boto3_client(
    service_name: str,
    profile: str | None = None,
    region: str | None = None,
    connect_timeout: int = 10,
    read_timeout: int = 30,
    max_retries: int = 3,
) -> Any:
    """Create a boto3 client with optional profile, region, and timeouts.

    F021: Added timeout configuration to prevent indefinite hangs on AWS API calls.

    Args:
        service_name: AWS service name (e.g., 'cloudwatch', 'secretsmanager')
        profile: AWS profile name (optional)
        region: AWS region (optional)
        connect_timeout: Connection timeout in seconds (default: 10)
        read_timeout: Read timeout in seconds (default: 30)
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        Configured boto3 client with timeouts
    """
    from botocore.config import Config

    session = get_boto3_session(profile=profile, region=region)

    # F021: Configure timeouts and retries to prevent indefinite hangs
    config = Config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_retries, "mode": "adaptive"},
    )

    return session.client(service_name, config=config)
