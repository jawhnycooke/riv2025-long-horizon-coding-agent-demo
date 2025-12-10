"""Orchestrator agent factory for coordinating the Worker subagent.

The Orchestrator is the "brain" of the system - it reads state, plans work,
and delegates atomic tasks to the Worker. This maps to the combined
"Initializer" + "Coding Agent" coordination role in Anthropic's article.

Design Principles:
    1. Read-only exploration - understands state before acting
    2. Task delegation - uses Task tool to invoke Worker for execution
    3. State management - reads/writes progress files, manages git
    4. Clean handoff - leaves state that next session can resume from
"""

import os
from pathlib import Path
from typing import Any

from claude_sdk import ClaudeSDKClient, ClaudeAgentOptions, HookMatcher

from src.agents.worker import WorkerAgent
from src.security import SecurityValidator
from src.tracing import get_tracing_manager


def create_orchestrator_client(
    args: Any,
    system_prompt: str,
    generation_dir: Path,
) -> ClaudeSDKClient:
    """Create and configure the Orchestrator agent with Worker subagent.

    The Orchestrator has limited tools - primarily read-only exploration
    plus the Task tool to delegate work to the Worker.

    Args:
        args: Command line arguments (must have .model attribute)
        system_prompt: System prompt for the Orchestrator
        generation_dir: Project directory path

    Returns:
        Configured ClaudeSDKClient with Worker as subagent
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

    # Create the Worker agent definition for the SDK
    worker = WorkerAgent()
    worker_definition = worker.to_sdk_definition()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=args.model,
            system_prompt=system_prompt,
            cli_path=cli_path,
            # Orchestrator tools: read-only exploration + Task delegation
            allowed_tools=[
                "think",      # Reasoning
                "Read",       # Read files
                "Glob",       # Find files
                "Grep",       # Search content
                "Write",      # Write files (for progress tracking)
                "Edit",       # Edit files
                "MultiEdit",  # Bulk edits
                "Bash",       # Commands (with security hooks)
                "Task",       # Delegate to Worker subagent
            ],
            disallowed_tools=[],
            # Register the Worker as a subagent
            agents={
                worker.name: worker_definition,
            },
            mcp_servers={},
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


def create_legacy_client(
    args: Any,
    system_prompt: str,
    generation_dir: Path,
) -> ClaudeSDKClient:
    """Create the original monolithic client without subagents.

    This is a fallback for testing and comparison purposes.
    Equivalent to the original _create_claude_client function.

    Args:
        args: Command line arguments
        system_prompt: System prompt for Claude
        generation_dir: Project directory path

    Returns:
        Configured ClaudeSDKClient (monolithic, no subagents)
    """
    project_root = str(generation_dir)

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

    # Tracing hooks
    active_spans: dict[str, Any] = {}

    async def tracing_pre_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
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

    cli_path = (
        "/usr/local/bin/claude" if os.path.exists("/usr/local/bin/claude") else None
    )

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=args.model,
            system_prompt=system_prompt,
            cli_path=cli_path,
            allowed_tools=[
                "think",
                "Read",
                "Glob",
                "Grep",
                "Write",
                "Edit",
                "MultiEdit",
                "Bash",
            ],
            disallowed_tools=[],
            mcp_servers={},
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="*", hooks=[universal_path_security_hook_wrapper]
                    ),
                    HookMatcher(matcher="*", hooks=[tracing_pre_hook]),
                ],
                "PostToolUse": [
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
