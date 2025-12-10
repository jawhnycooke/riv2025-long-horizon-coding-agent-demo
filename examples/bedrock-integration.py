#!/usr/bin/env python3
"""
AWS Bedrock AgentCore Integration Example

Demonstrates how to use Claude via AWS Bedrock instead of the
Anthropic API directly.

Usage:
    # Configure AWS credentials first
    aws configure

    # Run with Bedrock
    CLAUDE_CODE_USE_BEDROCK=1 python examples/bedrock-integration.py
"""

import os
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Bedrock Configuration
# =============================================================================


@dataclass
class BedrockConfig:
    """AWS Bedrock configuration."""

    region: str = "us-east-1"
    inference_profile: str | None = None
    model_id: str = "anthropic.claude-sonnet-4-20250514-v1:0"

    # Cross-region inference profile IDs
    INFERENCE_PROFILES: dict[str, str] = field(
        default_factory=lambda: {
            "us": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "eu": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
        }
    )

    def get_model_identifier(self) -> str:
        """Get the model identifier for Bedrock API calls."""
        if self.inference_profile:
            return self.inference_profile
        return self.model_id


@dataclass
class ProjectConfig:
    """Project configuration with provider settings."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    bedrock: BedrockConfig = field(default_factory=BedrockConfig)

    @classmethod
    def from_file(cls, path: str = ".claude-code.json") -> "ProjectConfig":
        """Load configuration from JSON file."""
        import json
        from pathlib import Path

        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = json.load(f)

        bedrock_data = data.get("bedrock", {})
        bedrock_config = BedrockConfig(
            region=bedrock_data.get("region", "us-east-1"),
            inference_profile=bedrock_data.get("inference_profile"),
        )

        return cls(
            provider=data.get("provider", "anthropic"),
            model=data.get("model", "claude-sonnet-4-20250514"),
            bedrock=bedrock_config,
        )


# =============================================================================
# Provider Selection
# =============================================================================


def is_bedrock_enabled() -> bool:
    """Check if Bedrock should be used."""
    # Environment variable override
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        return True

    # Check config file
    config = ProjectConfig.from_file()
    return config.provider == "bedrock"


def get_bedrock_client_config(config: ProjectConfig) -> dict[str, Any]:
    """
    Get configuration for Bedrock client.

    In real implementation, this would configure boto3 client.
    """
    return {
        "region_name": config.bedrock.region,
        "model_id": config.bedrock.get_model_identifier(),
        "service_name": "bedrock-runtime",
    }


def get_anthropic_client_config(config: ProjectConfig) -> dict[str, Any]:
    """
    Get configuration for Anthropic client.

    In real implementation, this would configure anthropic client.
    """
    api_key_var = os.environ.get("ANTHROPIC_API_KEY_ENV_VAR", "ANTHROPIC_API_KEY")
    return {
        "api_key": os.environ.get(api_key_var),
        "model": config.model,
    }


# =============================================================================
# Unified Client Interface
# =============================================================================


class UnifiedClaudeClient:
    """
    Unified client that works with both Anthropic and Bedrock.

    This is a simplified example - the real implementation uses
    the Claude SDK which handles this abstraction.
    """

    def __init__(self, config: ProjectConfig | None = None):
        self.config = config or ProjectConfig.from_file()
        self.provider = "bedrock" if is_bedrock_enabled() else self.config.provider

    def get_client_config(self) -> dict[str, Any]:
        """Get provider-specific client configuration."""
        if self.provider == "bedrock":
            return get_bedrock_client_config(self.config)
        return get_anthropic_client_config(self.config)

    def create_message(self, prompt: str, system: str = "") -> dict[str, Any]:
        """
        Create a message request.

        Returns the request structure - actual API call would happen here.
        """
        if self.provider == "bedrock":
            return self._create_bedrock_request(prompt, system)
        return self._create_anthropic_request(prompt, system)

    def _create_bedrock_request(self, prompt: str, system: str) -> dict[str, Any]:
        """Create Bedrock-formatted request."""
        return {
            "modelId": self.config.bedrock.get_model_identifier(),
            "contentType": "application/json",
            "accept": "application/json",
            "body": {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        }

    def _create_anthropic_request(self, prompt: str, system: str) -> dict[str, Any]:
        """Create Anthropic API-formatted request."""
        return {
            "model": self.config.model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }


# =============================================================================
# AWS Infrastructure Notes
# =============================================================================


AWS_SETUP_NOTES = """
AWS Bedrock Setup Requirements
==============================

1. IAM Permissions
------------------
Your IAM role/user needs:

{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
            ]
        }
    ]
}

2. Model Access
---------------
Enable Claude models in the Bedrock console:
- Go to AWS Console → Amazon Bedrock → Model access
- Request access to Anthropic Claude models
- Wait for approval (usually instant for Claude)

3. Region Selection
-------------------
Available regions for Claude:
- us-east-1 (N. Virginia)
- us-west-2 (Oregon)
- eu-west-1 (Ireland)
- ap-northeast-1 (Tokyo)

4. Cross-Region Inference
-------------------------
For higher throughput, use inference profiles:

{
    "bedrock": {
        "region": "us-east-1",
        "inference_profile": "us.anthropic.claude-sonnet-4-20250514-v1:0"
    }
}

5. Environment Variables
------------------------
# Option 1: AWS CLI configured credentials
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"

# Option 3: IAM role (for ECS/Lambda)
# Automatically uses task/function role

6. Cost Considerations
----------------------
Bedrock pricing differs from Anthropic API:
- No monthly minimum
- Pay per token (input/output priced separately)
- Cross-region inference may have different pricing
"""


# =============================================================================
# Example Usage
# =============================================================================


def main() -> None:
    """Demonstrate Bedrock integration."""
    import json

    print("AWS Bedrock Integration")
    print("=" * 50)

    # Check provider
    provider = "bedrock" if is_bedrock_enabled() else "anthropic"
    print(f"Current provider: {provider}")

    # Load/create config
    config = ProjectConfig.from_file()
    print(f"Model: {config.model}")

    if provider == "bedrock":
        print(f"Region: {config.bedrock.region}")
        print(f"Model ID: {config.bedrock.get_model_identifier()}")

    # Create client
    client = UnifiedClaudeClient(config)
    print(f"\nClient config:")
    print(json.dumps(client.get_client_config(), indent=2, default=str))

    # Example request
    print(f"\nExample request structure ({provider}):")
    request = client.create_message(
        prompt="Implement a login form component",
        system="You are a helpful coding assistant.",
    )
    print(json.dumps(request, indent=2))

    print("\n" + "=" * 50)
    print("Configuration File (.claude-code.json)")
    print("=" * 50)
    print(
        """
For Anthropic API:
{
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "anthropic": {
        "api_key_env_var": "ANTHROPIC_API_KEY"
    }
}

For AWS Bedrock:
{
    "provider": "bedrock",
    "model": "claude-sonnet-4-20250514",
    "bedrock": {
        "region": "us-east-1",
        "inference_profile": null
    }
}
"""
    )

    print("=" * 50)
    print("AWS Setup Notes")
    print("=" * 50)
    print(AWS_SETUP_NOTES)


if __name__ == "__main__":
    main()
