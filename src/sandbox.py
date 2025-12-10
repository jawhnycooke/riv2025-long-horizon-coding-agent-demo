"""SDK Sandbox configuration for security.

This module provides SDK-native sandbox settings that replace custom
security hooks where possible. The SandboxSettings provide:
- Path restrictions (files outside project blocked)
- Command allowlisting (dangerous commands blocked)
- Network restrictions (configurable)

Note: The track_read_hook for screenshot verification MUST remain as a
custom hook because it maintains stateful verification tracking.
"""

from pathlib import Path
from typing import Any


# Sandbox configuration for the SDK
# Note: This is a placeholder structure until the SDK's SandboxSettings
# API is finalized. Current implementation uses custom hooks.

EXCLUDED_COMMANDS = [
    # Dangerous system commands
    "docker",
    "sudo",
    "su",
    "chmod",
    "chown",
    # Destructive commands without safeguards
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "mkfs",
    "dd",
    # Network commands that could be misused
    "curl | bash",
    "wget | bash",
    "nc -l",
    "netcat -l",
]


ALLOWED_COMMANDS = [
    # Package management
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "pip",
    "uv",
    "uvx",
    # Development
    "node",
    "python",
    "python3",
    # Testing
    "playwright",
    "pytest",
    "jest",
    "vitest",
    # Build tools
    "vite",
    "webpack",
    "esbuild",
    "tsc",
    # Version control
    "git",
    # File operations (safe)
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "mkdir",
    "cp",
    "mv",
    "touch",
    # System info
    "pwd",
    "which",
    "echo",
    "env",
    "printenv",
    # Process management
    "ps",
    "kill",
    "pkill",
    "lsof",
]


def get_sandbox_settings(project_root: Path) -> dict[str, Any]:
    """Get SDK sandbox settings for the given project.

    Note: This returns a configuration dict that can be passed to
    the SDK when SandboxSettings is available. Currently, security
    is enforced via custom hooks.

    Args:
        project_root: The project directory to sandbox

    Returns:
        Configuration dict for SDK SandboxSettings
    """
    return {
        "enabled": True,
        "project_root": str(project_root),
        "auto_allow_bash_if_sandboxed": True,
        "excluded_commands": EXCLUDED_COMMANDS,
        "allowed_commands": ALLOWED_COMMANDS,
        "network": {
            "allow_local_binding": True,  # For dev servers
            "allowed_hosts": [
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                # GitHub for git operations
                "github.com",
                "api.github.com",
                # npm registry
                "registry.npmjs.org",
                # Anthropic API
                "api.anthropic.com",
            ],
        },
        "filesystem": {
            "allowed_paths": [
                str(project_root),
                # Allow reading from common tool paths
                "/usr/bin",
                "/usr/local/bin",
                "/opt/homebrew/bin",
            ],
            "blocked_paths": [
                # Block sensitive system directories
                "/etc/passwd",
                "/etc/shadow",
                "~/.ssh",
                "~/.aws/credentials",
                "~/.gnupg",
            ],
        },
    }


def validate_sandbox_security(
    command: str,
    project_root: Path,
) -> tuple[bool, str]:
    """Validate a command against sandbox security rules.

    This mirrors the logic that would be in SandboxSettings,
    allowing for comparison during the migration phase.

    Args:
        command: The bash command to validate
        project_root: The project directory

    Returns:
        Tuple of (is_allowed, reason)
    """
    command_lower = command.lower().strip()

    # Check excluded commands
    for excluded in EXCLUDED_COMMANDS:
        if excluded in command_lower:
            return False, f"Command contains excluded pattern: {excluded}"

    # Check if command starts with an allowed prefix
    command_base = command_lower.split()[0] if command_lower.split() else ""
    command_base = command_base.split("/")[-1]  # Handle full paths

    if command_base not in ALLOWED_COMMANDS:
        return False, f"Command '{command_base}' not in allowed commands list"

    return True, "Command allowed"


def compare_security_decisions(
    hook_decision: tuple[bool, str],
    sandbox_decision: tuple[bool, str],
    command: str,
) -> dict[str, Any]:
    """Compare security decisions between hooks and sandbox.

    Used during migration to validate that the SDK sandbox
    provides equivalent security to custom hooks.

    Args:
        hook_decision: (allowed, reason) from custom hook
        sandbox_decision: (allowed, reason) from sandbox check
        command: The command being evaluated

    Returns:
        Comparison result dict with any discrepancies
    """
    hook_allowed, hook_reason = hook_decision
    sandbox_allowed, sandbox_reason = sandbox_decision

    result = {
        "command": command,
        "hook_allowed": hook_allowed,
        "hook_reason": hook_reason,
        "sandbox_allowed": sandbox_allowed,
        "sandbox_reason": sandbox_reason,
        "match": hook_allowed == sandbox_allowed,
    }

    if not result["match"]:
        result["discrepancy"] = (
            f"Hook says {'ALLOW' if hook_allowed else 'BLOCK'}, "
            f"Sandbox says {'ALLOW' if sandbox_allowed else 'BLOCK'}"
        )

    return result
