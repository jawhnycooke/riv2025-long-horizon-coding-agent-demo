"""Audit trail logging for Claude Code Agent.

Provides secure logging of all agent actions for security review and debugging.
Uses JSON Lines format for easy parsing and rotation to manage disk space.

Key features:
- JSONL format (one JSON object per line) for easy parsing
- Rotating file handler (10MB max, 5 backups = 50MB total)
- Event types: bash_command, bash_blocked, file_read, file_write, file_blocked
- Timestamps in ISO 8601 format
- Structured data with tool name, input, outcome
"""

import contextlib
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class AuditEventType(str, Enum):
    """Types of audit events."""

    BASH_COMMAND = "bash_command"
    BASH_BLOCKED = "bash_blocked"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_BLOCKED = "file_blocked"
    EDIT_TOOL = "edit_tool"
    EDIT_BLOCKED = "edit_blocked"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class AuditLogger:
    """Audit logger for agent actions.

    Logs all bash commands, file operations, and blocked actions to a
    rotating JSON Lines file for security review.
    """

    # Configuration
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
    BACKUP_COUNT = 5  # 5 backup files = 50 MB total

    def __init__(
        self,
        log_dir: Path | str | None = None,
        log_file: str = "audit.jsonl",
        enabled: bool = True,
    ) -> None:
        """Initialize audit logger.

        Args:
            log_dir: Directory for audit log. Defaults to current directory.
            log_file: Name of the audit log file.
            enabled: Whether audit logging is enabled.
        """
        self.enabled = enabled
        self._logger: logging.Logger | None = None

        if not enabled:
            return

        # Set up log directory
        if log_dir is None:
            log_dir = Path.cwd()
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_file

        # Configure rotating file handler
        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't send to root logger

        # Remove existing handlers
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)

        # Add rotating file handler
        handler = RotatingFileHandler(
            log_path,
            maxBytes=self.MAX_BYTES,
            backupCount=self.BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

        self.log_path = log_path

    def _log_event(
        self,
        event_type: AuditEventType,
        tool_name: str,
        input_data: dict[str, Any],
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event.

        Args:
            event_type: Type of audit event
            tool_name: Name of the tool being used
            input_data: Tool input data (sanitized)
            outcome: Result of the operation (allowed, blocked, success, error)
            details: Additional details about the event
        """
        if not self.enabled or self._logger is None:
            return

        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type.value,
            "tool_name": tool_name,
            "input": self._sanitize_input(input_data),
            "outcome": outcome,
        }

        if details:
            event["details"] = details

        # Don't let audit logging failures break the agent
        with contextlib.suppress(Exception):
            self._logger.info(json.dumps(event, default=str))

    def _sanitize_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize input data to avoid logging sensitive information.

        Args:
            input_data: Raw input data

        Returns:
            Sanitized input data
        """
        sanitized = {}
        sensitive_keys = {"token", "password", "secret", "key", "api_key", "auth"}

        for key, value in input_data.items():
            # Mask sensitive values
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 1000:
                # Truncate very long values
                sanitized[key] = value[:1000] + "...[truncated]"
            else:
                sanitized[key] = value

        return sanitized

    def log_bash_command(
        self,
        command: str,
        exit_code: int | None = None,
        blocked: bool = False,
        reason: str | None = None,
    ) -> None:
        """Log a bash command execution.

        Args:
            command: The bash command that was executed or attempted
            exit_code: Exit code if command was executed
            blocked: Whether the command was blocked
            reason: Reason for blocking (if blocked)
        """
        event_type = (
            AuditEventType.BASH_BLOCKED if blocked else AuditEventType.BASH_COMMAND
        )
        outcome = (
            "blocked"
            if blocked
            else ("success" if exit_code == 0 else f"exit_{exit_code}")
        )

        details: dict[str, Any] = {}
        if exit_code is not None:
            details["exit_code"] = exit_code
        if reason:
            details["reason"] = reason

        self._log_event(
            event_type=event_type,
            tool_name="Bash",
            input_data={"command": command},
            outcome=outcome,
            details=details if details else None,
        )

    def log_file_operation(
        self,
        operation: str,
        file_path: str,
        blocked: bool = False,
        reason: str | None = None,
    ) -> None:
        """Log a file operation.

        Args:
            operation: Type of operation (read, write, edit)
            file_path: Path to the file
            blocked: Whether the operation was blocked
            reason: Reason for blocking (if blocked)
        """
        event_type_map = {
            "read": (AuditEventType.FILE_READ, AuditEventType.FILE_BLOCKED),
            "write": (AuditEventType.FILE_WRITE, AuditEventType.FILE_BLOCKED),
            "edit": (AuditEventType.EDIT_TOOL, AuditEventType.EDIT_BLOCKED),
        }

        allowed_type, blocked_type = event_type_map.get(
            operation, (AuditEventType.FILE_READ, AuditEventType.FILE_BLOCKED)
        )
        event_type = blocked_type if blocked else allowed_type
        outcome = "blocked" if blocked else "allowed"

        details = {"reason": reason} if reason else None

        self._log_event(
            event_type=event_type,
            tool_name=operation.title(),
            input_data={"file_path": file_path},
            outcome=outcome,
            details=details,
        )

    def log_session_start(
        self,
        session_id: str | None = None,
        project: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Log session start.

        Args:
            session_id: Unique session identifier
            project: Project name
            provider: Model provider (anthropic, bedrock)
        """
        details = {}
        if session_id:
            details["session_id"] = session_id
        if project:
            details["project"] = project
        if provider:
            details["provider"] = provider

        self._log_event(
            event_type=AuditEventType.SESSION_START,
            tool_name="Session",
            input_data={},
            outcome="started",
            details=details if details else None,
        )

    def log_session_end(
        self,
        session_id: str | None = None,
        reason: str = "completed",
    ) -> None:
        """Log session end.

        Args:
            session_id: Unique session identifier
            reason: Reason for session end (completed, error, terminated)
        """
        details = {}
        if session_id:
            details["session_id"] = session_id

        self._log_event(
            event_type=AuditEventType.SESSION_END,
            tool_name="Session",
            input_data={},
            outcome=reason,
            details=details if details else None,
        )

    def close(self) -> None:
        """Close the audit logger and flush handlers."""
        if self._logger:
            for handler in self._logger.handlers[:]:
                handler.close()
                self._logger.removeHandler(handler)


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance.

    Returns:
        The global AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(enabled=False)  # Disabled by default
    return _audit_logger


def init_audit_logger(
    log_dir: Path | str | None = None,
    enabled: bool = True,
) -> AuditLogger:
    """Initialize the global audit logger.

    Args:
        log_dir: Directory for audit log
        enabled: Whether audit logging is enabled

    Returns:
        The initialized AuditLogger instance
    """
    global _audit_logger
    _audit_logger = AuditLogger(log_dir=log_dir, enabled=enabled)
    return _audit_logger
