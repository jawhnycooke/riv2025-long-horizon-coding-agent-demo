#!/usr/bin/env python3
"""
Claude Code Agent - Interactive Setup Wizard

Menu-driven CLI installer for configuring the model provider (Anthropic API or Amazon Bedrock).
Configuration is persisted to .claude-code.json in the project directory.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


try:
    import questionary
    from questionary import Style
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Error: Required packages not installed.")
    print("Please run: uv pip install -r requirements.txt")
    sys.exit(1)


# Initialize rich console
console = Console()

# Custom questionary style
custom_style = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
    ]
)

# Configuration file path
CONFIG_FILE = Path(".claude-code.json")

# Provider definitions
PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Direct API)",
        "description": "Use Anthropic's first-party API directly",
    },
    "bedrock": {
        "name": "Amazon Bedrock",
        "description": "Use Claude via AWS Bedrock (requires AWS credentials)",
    },
}

# Model definitions per provider
MODELS = {
    "anthropic": [
        {
            "id": "claude-opus-4-5-20251101",
            "name": "Claude Opus 4.5",
            "description": "Most capable model, best for complex tasks",
        },
        {
            "id": "claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "description": "Balanced performance and cost",
        },
        {
            "id": "claude-haiku-4-5-20250927",
            "name": "Claude Haiku 4.5",
            "description": "Fastest and most cost-effective",
        },
    ],
    "bedrock": [
        {
            "id": "claude-opus-4-5-20251101",
            "name": "Claude Opus 4.5",
            "description": "Most capable model, best for complex tasks",
        },
        {
            "id": "claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "description": "Balanced performance and cost",
        },
        {
            "id": "claude-haiku-4-5-20250927",
            "name": "Claude Haiku 4.5",
            "description": "Fastest and most cost-effective",
        },
    ],
}

# Bedrock regions (prioritized)
BEDROCK_REGIONS = [
    {"id": "us-east-1", "name": "US East (N. Virginia)"},
    {"id": "us-west-2", "name": "US West (Oregon)"},
    {"id": "eu-west-1", "name": "Europe (Ireland)"},
    {"id": "ap-northeast-1", "name": "Asia Pacific (Tokyo)"},
    {"id": "ap-southeast-2", "name": "Asia Pacific (Sydney)"},
]

# Default AWS profile if none detected
DEFAULT_AWS_PROFILE = "ClaudeCode"


def detect_aws_profile() -> str:
    """Detect the current AWS profile.

    Checks in order:
    1. AWS_PROFILE environment variable
    2. AWS_DEFAULT_PROFILE environment variable
    3. Default profile from AWS CLI config
    4. Falls back to DEFAULT_AWS_PROFILE ("ClaudeCode")

    Returns:
        The detected AWS profile name or default.
    """
    # Check environment variables first
    profile = os.environ.get("AWS_PROFILE") or os.environ.get("AWS_DEFAULT_PROFILE")
    if profile:
        return profile

    # Try to get profile from AWS CLI
    try:
        result = subprocess.run(
            ["aws", "configure", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "profile" in line.lower():
                    parts = line.split()
                    # Format: "profile <value> <source> <path>"
                    if len(parts) >= 2 and parts[1] != "<not":
                        return parts[1]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return DEFAULT_AWS_PROFILE


def load_existing_config() -> dict[str, Any] | None:
    """Load existing configuration if present."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_config(config: dict[str, Any]) -> bool:
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError as e:
        console.print(f"[red]Error saving configuration: {e}[/red]")
        return False


def display_header() -> None:
    """Display the setup wizard header."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Claude Code Agent - Setup Wizard[/bold cyan]",
            expand=False,
            border_style="cyan",
        )
    )
    console.print()


def display_current_config(config: dict[str, Any]) -> None:
    """Display current configuration summary."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Setting", style="dim")
    table.add_column("Value", style="cyan")

    provider_name = PROVIDERS.get(config.get("provider", ""), {}).get(
        "name", config.get("provider", "Unknown")
    )
    table.add_row("Provider", provider_name)
    table.add_row("Model", config.get("model", "Unknown"))

    if config.get("provider") == "bedrock":
        bedrock_config = config.get("bedrock", {})
        table.add_row("AWS Profile", bedrock_config.get("profile", "Not set"))
        table.add_row("AWS Region", bedrock_config.get("region", "Not set"))

    console.print(table)


def display_success(config: dict[str, Any]) -> None:
    """Display success message with next steps."""
    console.print()
    console.print("[green]Configuration saved to .claude-code.json[/green]")
    console.print()

    # Next steps panel
    if config.get("provider") == "anthropic":
        next_steps = (
            "1. Set ANTHROPIC_API_KEY environment variable\n"
            "2. Run: python agent.py --project <name>"
        )
    else:
        next_steps = (
            "1. Ensure AWS credentials are configured\n"
            "   (aws configure or IAM role)\n"
            "2. Run: python agent.py --project <name>"
        )

    console.print(
        Panel(
            next_steps,
            title="[bold]Next Steps[/bold]",
            border_style="green",
            expand=False,
        )
    )
    console.print()


def handle_existing_config(config: dict[str, Any]) -> str | None:
    """Handle existing configuration - ask user what to do."""
    console.print("[yellow]Existing configuration found: .claude-code.json[/yellow]")
    console.print()
    console.print("[dim]Current settings:[/dim]")
    display_current_config(config)
    console.print()

    action = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Update configuration", value="update"),
            questionary.Choice("Start fresh (overwrite)", value="overwrite"),
            questionary.Choice("Cancel", value="cancel"),
        ],
        style=custom_style,
    ).ask()

    return action


def select_provider(current: str | None = None) -> str | None:
    """Prompt user to select a provider."""
    choices = [
        questionary.Choice(
            f"{info['name']} - {info['description']}",
            value=provider_id,
        )
        for provider_id, info in PROVIDERS.items()
    ]

    default = current if current in PROVIDERS else "bedrock"

    return questionary.select(
        "Select your model provider:",
        choices=choices,
        default=default,
        style=custom_style,
    ).ask()


def select_model(provider: str, current: str | None = None) -> str | None:
    """Prompt user to select a model for the given provider."""
    models = MODELS.get(provider, [])

    choices = [
        questionary.Choice(
            f"{model['name']} - {model['description']}",
            value=model["id"],
        )
        for model in models
    ]

    # Find default based on current model, or use Sonnet 4.5
    default = "claude-sonnet-4-5-20250929"
    if current:
        for model in models:
            if model["id"] == current:
                default = current
                break

    return questionary.select(
        "Select model:",
        choices=choices,
        default=default,
        style=custom_style,
    ).ask()


def select_bedrock_region(current: str | None = None) -> str | None:
    """Prompt user to select an AWS region for Bedrock."""
    choices = [
        questionary.Choice(
            f"{region['id']} ({region['name']})",
            value=region["id"],
        )
        for region in BEDROCK_REGIONS
    ]

    default = current if current in [r["id"] for r in BEDROCK_REGIONS] else "us-east-1"

    return questionary.select(
        "Select AWS region:",
        choices=choices,
        default=default,
        style=custom_style,
    ).ask()


def select_aws_profile(detected_profile: str, current: str | None = None) -> str | None:
    """Prompt user to confirm or change AWS profile.

    Args:
        detected_profile: The auto-detected AWS profile.
        current: The current profile from existing config.

    Returns:
        The selected AWS profile name or None if cancelled.
    """
    # Use current config value if available, otherwise use detected
    default_profile = current if current else detected_profile
    is_detected = current is None

    if is_detected:
        console.print(
            f"[dim]Detected AWS profile: [cyan]{detected_profile}[/cyan][/dim]"
        )
    else:
        console.print(f"[dim]Current AWS profile: [cyan]{current}[/cyan][/dim]")

    action = questionary.select(
        "AWS profile configuration:",
        choices=[
            questionary.Choice(
                f"Use {'detected' if is_detected else 'current'} profile ({default_profile})",
                value="use_default",
            ),
            questionary.Choice(
                "Enter a different profile name",
                value="custom",
            ),
        ],
        style=custom_style,
    ).ask()

    if action is None:
        return None
    elif action == "use_default":
        return default_profile
    else:
        custom_profile = questionary.text(
            "Enter AWS profile name:",
            default=default_profile,
            style=custom_style,
        ).ask()
        return custom_profile


def select_api_key_method() -> str | None:
    """Prompt user how they want to provide API key."""
    return questionary.select(
        "How will you provide your API key?",
        choices=[
            questionary.Choice(
                "Environment variable (ANTHROPIC_API_KEY)",
                value="env",
            ),
            questionary.Choice(
                "Enter now (stored in config - not recommended for shared repos)",
                value="direct",
            ),
        ],
        default="direct",
        style=custom_style,
    ).ask()


def get_api_key() -> str | None:
    """Prompt user to enter API key directly."""
    return questionary.password(
        "Enter your Anthropic API key:",
        style=custom_style,
    ).ask()


def run_wizard(
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run the interactive setup wizard."""
    config: dict[str, Any] = {}

    # Use existing values as defaults if updating
    current_provider = existing_config.get("provider") if existing_config else None
    current_model = existing_config.get("model") if existing_config else None
    current_bedrock = existing_config.get("bedrock", {}) if existing_config else {}
    current_anthropic = existing_config.get("anthropic", {}) if existing_config else {}

    # Step 1: Select provider
    provider = select_provider(current_provider)
    if not provider:
        return None
    config["provider"] = provider

    # Step 2: Provider-specific configuration
    if provider == "bedrock":
        # Detect and select AWS profile
        detected_profile = detect_aws_profile()
        aws_profile = select_aws_profile(
            detected_profile, current_bedrock.get("profile")
        )
        if not aws_profile:
            return None

        # Select region
        region = select_bedrock_region(current_bedrock.get("region"))
        if not region:
            return None

        config["bedrock"] = {
            "region": region,
            "profile": aws_profile,
            "inference_profile": current_bedrock.get("inference_profile"),
        }

        # Preserve anthropic config if it existed
        if current_anthropic:
            config["anthropic"] = current_anthropic

    else:  # anthropic
        # Ask about API key method
        api_key_method = select_api_key_method()
        if not api_key_method:
            return None

        anthropic_config: dict[str, Any] = {
            "api_key_env_var": "ANTHROPIC_API_KEY",
        }

        if api_key_method == "direct":
            api_key = get_api_key()
            if api_key:
                anthropic_config["api_key"] = api_key
                console.print(
                    "[yellow]Warning: API key stored in config file. "
                    "Ensure .claude-code.json is in .gitignore[/yellow]"
                )

        config["anthropic"] = anthropic_config

        # Preserve bedrock config if it existed
        if current_bedrock:
            config["bedrock"] = current_bedrock

    # Step 3: Select model
    model = select_model(provider, current_model)
    if not model:
        return None
    config["model"] = model

    return config


def main() -> int:
    """Main entry point for the setup wizard."""
    display_header()

    # Check for existing configuration
    existing_config = load_existing_config()

    if existing_config:
        action = handle_existing_config(existing_config)

        if action == "cancel":
            console.print("[dim]Setup cancelled.[/dim]")
            return 0
        elif action == "update":
            # Run wizard with existing config as defaults
            new_config = run_wizard(existing_config)
        else:  # overwrite
            new_config = run_wizard()
    else:
        new_config = run_wizard()

    if not new_config:
        console.print("[dim]Setup cancelled.[/dim]")
        return 0

    # Save configuration
    if save_config(new_config):
        display_success(new_config)
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
