"""Agent client factory for Claude SDK.

Creates a configured ClaudeSDKClient with security hooks, tracing,
and tool restrictions for the long-horizon coding agent.
"""

import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, HookMatcher

from src.security import SecurityValidator
from src.tracing import get_tracing_manager


def create_agent_client(
    args: Any,
    system_prompt: str,
    generation_dir: Path,
) -> ClaudeSDKClient:
    """Create and configure the Claude agent client.

    Args:
        args: Command line arguments (must have .model attribute)
        system_prompt: System prompt for Claude
        generation_dir: Project directory path

    Returns:
        Configured ClaudeSDKClient
    """
    project_root = str(generation_dir)

    # Create security hook wrappers that capture project_root
    async def universal_path_security_hook_wrapper(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        return await SecurityValidator.universal_path_security_hook(
            input_data, tool_use_id, context, project_root
        )

    async def track_read_hook_wrapper(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        return await SecurityValidator.track_read_hook(
            input_data, tool_use_id, context, project_root
        )

    async def bash_security_hook_wrapper(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        return await SecurityValidator.bash_security_hook(
            input_data, tool_use_id, context, project_root
        )

    async def cd_enforcement_hook_wrapper(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        return await SecurityValidator.cd_enforcement_hook(
            input_data, tool_use_id, context, project_root
        )

    # Tracing hooks for OpenTelemetry integration
    active_spans: dict[str, Any] = {}

    async def tracing_pre_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        """Start a tracing span before tool execution."""
        tracing = get_tracing_manager()
        if not tracing.is_enabled:
            return input_data

        tool_name = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {})

        tracer = tracing.trace_tool_call(tool_name, tool_input)
        tracer.__enter__()

        if tool_use_id:
            active_spans[tool_use_id] = tracer

        return input_data

    async def tracing_post_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        """End the tracing span after tool execution."""
        if not tool_use_id or tool_use_id not in active_spans:
            return input_data

        tracer = active_spans.pop(tool_use_id)

        tool_result = input_data.get("tool_result", {})
        if isinstance(tool_result, dict):
            is_error = tool_result.get("is_error", False)
            content = tool_result.get("content", "")
            if is_error:
                error_msg = str(content)[:200] if content else "Unknown error"
                tracer.set_error(error_msg)
            else:
                result_preview = str(content)[:200] if content else ""
                tracer.set_success(result_preview)

        tracer.__exit__(None, None, None)
        return input_data

    # For Docker/AWS deployment: explicitly set CLI path if in containerized environment
    cli_path = (
        "/usr/local/bin/claude" if os.path.exists("/usr/local/bin/claude") else None
    )

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=args.model,
            system_prompt=system_prompt,
            cli_path=cli_path,
            allowed_tools=[
                "think",      # Reasoning
                "Read",       # Read files
                "Glob",       # Find files
                "Grep",       # Search content
                "Write",      # Write files
                "Edit",       # Edit files
                "MultiEdit",  # Bulk edits
                "Bash",       # Commands (with security hooks)
            ],
            disallowed_tools=[],
            mcp_servers={},
            # Bypass permission prompts for headless container execution
            # Security is enforced via hooks below, not interactive prompts
            # See: https://platform.claude.com/docs/en/agent-sdk/permissions
            permission_mode="bypassPermissions",
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="*", hooks=[universal_path_security_hook_wrapper]
                    ),
                    HookMatcher(matcher="*", hooks=[tracing_pre_hook]),
                ],
                "PostToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook_wrapper]),
                    HookMatcher(matcher="Bash", hooks=[cd_enforcement_hook_wrapper]),
                    HookMatcher(matcher="Read", hooks=[track_read_hook_wrapper]),
                    HookMatcher(matcher="*", hooks=[tracing_post_hook]),
                ],
            },
            max_turns=10000,
            cwd=str(generation_dir),
            add_dirs=[str(generation_dir / "prompts")],
        )
    )
