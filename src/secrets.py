"""AWS Secrets Manager utilities for Claude Code Agent.

Provides functions to fetch secrets from AWS Secrets Manager,
including Anthropic API keys, Bedrock API keys, and GitHub tokens.
"""

import os
from pathlib import Path

from .config import get_boto3_client

# File paths for git hook communication
GITHUB_TOKEN_FILE = Path("/tmp/github_token.txt")

# Environment variable for Bedrock API key authentication
# See: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
BEDROCK_API_KEY_ENV_VAR = "AWS_BEARER_TOKEN_BEDROCK"


def get_secret(secret_name: str, profile: str | None = None) -> str | None:
    """Fetch secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret
        profile: AWS profile name (optional, falls back to AWS_PROFILE env var)

    Returns:
        Secret value or None if failed
    """
    try:
        client = get_boto3_client("secretsmanager", profile=profile)
        response = client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
    except Exception as e:
        print(f"❌ Failed to fetch secret {secret_name}: {e}")
        return None


def get_anthropic_api_key(environment: str | None = None) -> str | None:
    """Fetch Anthropic API key from Secrets Manager.

    Args:
        environment: Environment name (optional, defaults to ENVIRONMENT env var)

    Returns:
        API key or None if not found
    """
    env = environment or os.environ.get("ENVIRONMENT", "reinvent")
    return get_secret(f"claude-code/{env}/anthropic-api-key")


def get_bedrock_api_key(environment: str | None = None) -> str | None:
    """Fetch Bedrock API key from Secrets Manager.

    Bedrock API keys provide a simpler authentication method compared to
    IAM credentials. The key should be set in the AWS_BEARER_TOKEN_BEDROCK
    environment variable for SDK usage.

    See: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html

    Args:
        environment: Environment name (optional, defaults to ENVIRONMENT env var)

    Returns:
        API key or None if not found
    """
    env = environment or os.environ.get("ENVIRONMENT", "reinvent")
    return get_secret(f"claude-code/{env}/bedrock-api-key")


def get_github_token(github_repo: str | None = None, environment: str | None = None) -> str | None:
    """Fetch GitHub token from Secrets Manager.

    Checks for org-specific token first (e.g., github-token-anthropics),
    then falls back to the default github-token secret.

    Args:
        github_repo: GitHub repo in "org/repo" format. If provided, will check
                     for org-specific token first.
        environment: Environment name (optional, defaults to ENVIRONMENT env var)

    Returns:
        GitHub token or None if not found
    """
    env = environment or os.environ.get("ENVIRONMENT", "reinvent")
    repo = github_repo or os.environ.get("GITHUB_REPOSITORY", "")

    # Try org-specific token first (e.g., claude-code/reinvent/github-token-anthropics)
    if repo and "/" in repo:
        org = repo.split("/")[0]
        token = get_secret(f"claude-code/{env}/github-token-{org}")
        if token:
            print(f"✅ Using org-specific GitHub token for {org}")
            return token

    # Fall back to default token
    return get_secret(f"claude-code/{env}/github-token")


def write_github_token_to_file(github_token: str) -> bool:
    """Write GitHub token to a file for the post-commit hook to read.

    The post-commit hook needs access to the GitHub token to push commits.
    This function writes the token to a known location that the hook can read.

    Args:
        github_token: The GitHub token to write

    Returns:
        True if successful, False otherwise
    """
    try:
        GITHUB_TOKEN_FILE.write_text(github_token)
        # Set restrictive permissions
        GITHUB_TOKEN_FILE.chmod(0o600)
        return True
    except Exception as e:
        print(f"❌ Failed to write GitHub token file: {e}")
        return False


def read_github_token_from_file() -> str | None:
    """Read GitHub token from file (used by post-commit hook).

    Returns:
        GitHub token or None if file doesn't exist or is empty
    """
    try:
        if GITHUB_TOKEN_FILE.exists():
            token = GITHUB_TOKEN_FILE.read_text().strip()
            return token if token else None
        return None
    except Exception as e:
        print(f"❌ Failed to read GitHub token file: {e}")
        return None


def cleanup_token_file() -> None:
    """Remove the GitHub token file for security."""
    try:
        if GITHUB_TOKEN_FILE.exists():
            GITHUB_TOKEN_FILE.unlink()
    except Exception:
        pass  # Best effort cleanup
