"""Tests for src/audit.py - Audit trail logging."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from src.audit import (
    AuditEventType,
    AuditLogger,
    get_audit_logger,
    init_audit_logger,
)


@pytest.fixture
def audit_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for audit logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def enabled_logger(audit_dir: Path) -> Generator[AuditLogger, None, None]:
    """Create an enabled audit logger for testing."""
    logger = AuditLogger(log_dir=audit_dir, enabled=True)
    yield logger
    logger.close()


@pytest.fixture
def disabled_logger() -> AuditLogger:
    """Create a disabled audit logger for testing."""
    return AuditLogger(enabled=False)


class TestAuditEventType:
    """Tests for AuditEventType enum."""

    def test_event_types_are_strings(self) -> None:
        """Event types should be strings for JSON serialization."""
        assert AuditEventType.BASH_COMMAND.value == "bash_command"
        assert AuditEventType.BASH_BLOCKED.value == "bash_blocked"
        assert AuditEventType.FILE_READ.value == "file_read"
        assert AuditEventType.FILE_WRITE.value == "file_write"
        assert AuditEventType.FILE_BLOCKED.value == "file_blocked"
        assert AuditEventType.EDIT_TOOL.value == "edit_tool"
        assert AuditEventType.EDIT_BLOCKED.value == "edit_blocked"
        assert AuditEventType.SESSION_START.value == "session_start"
        assert AuditEventType.SESSION_END.value == "session_end"


class TestAuditLoggerInit:
    """Tests for AuditLogger initialization."""

    def test_enabled_logger_creates_file(self, audit_dir: Path) -> None:
        """Enabled logger should create the audit log file."""
        logger = AuditLogger(log_dir=audit_dir, enabled=True)
        assert logger.log_path.exists()
        logger.close()

    def test_disabled_logger_no_file(self) -> None:
        """Disabled logger should not create any files."""
        logger = AuditLogger(enabled=False)
        assert logger._logger is None

    def test_custom_log_file_name(self, audit_dir: Path) -> None:
        """Logger should use custom log file name."""
        logger = AuditLogger(log_dir=audit_dir, log_file="custom.jsonl", enabled=True)
        assert logger.log_path.name == "custom.jsonl"
        logger.close()

    def test_creates_log_directory(self) -> None:
        """Logger should create log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "subdir" / "logs"
            logger = AuditLogger(log_dir=new_dir, enabled=True)
            assert new_dir.exists()
            logger.close()


class TestLogBashCommand:
    """Tests for log_bash_command method."""

    def test_log_allowed_command(self, enabled_logger: AuditLogger) -> None:
        """Log an allowed bash command."""
        enabled_logger.log_bash_command("ls -la", exit_code=0, blocked=False)

        # Read the log
        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "bash_command"
        assert log_entry["tool_name"] == "Bash"
        assert log_entry["input"]["command"] == "ls -la"
        assert log_entry["outcome"] == "success"
        assert log_entry["details"]["exit_code"] == 0

    def test_log_blocked_command(self, enabled_logger: AuditLogger) -> None:
        """Log a blocked bash command."""
        enabled_logger.log_bash_command(
            "sudo rm -rf /", blocked=True, reason="Command not allowed"
        )

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "bash_blocked"
        assert log_entry["outcome"] == "blocked"
        assert log_entry["details"]["reason"] == "Command not allowed"

    def test_log_command_with_nonzero_exit(self, enabled_logger: AuditLogger) -> None:
        """Log a command with non-zero exit code."""
        enabled_logger.log_bash_command("exit 1", exit_code=1)

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["outcome"] == "exit_1"

    def test_disabled_logger_no_op(self, disabled_logger: AuditLogger) -> None:
        """Disabled logger should not write anything."""
        disabled_logger.log_bash_command("ls -la")
        # Should not raise, just be a no-op


class TestLogFileOperation:
    """Tests for log_file_operation method."""

    def test_log_read_operation(self, enabled_logger: AuditLogger) -> None:
        """Log a file read operation."""
        enabled_logger.log_file_operation("read", "/project/src/main.py")

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "file_read"
        assert log_entry["tool_name"] == "Read"
        assert log_entry["input"]["file_path"] == "/project/src/main.py"
        assert log_entry["outcome"] == "allowed"

    def test_log_write_operation(self, enabled_logger: AuditLogger) -> None:
        """Log a file write operation."""
        enabled_logger.log_file_operation("write", "/project/config.json")

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "file_write"
        assert log_entry["tool_name"] == "Write"

    def test_log_edit_operation(self, enabled_logger: AuditLogger) -> None:
        """Log a file edit operation."""
        enabled_logger.log_file_operation("edit", "/project/src/utils.py")

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "edit_tool"
        assert log_entry["tool_name"] == "Edit"

    def test_log_blocked_file_operation(self, enabled_logger: AuditLogger) -> None:
        """Log a blocked file operation."""
        enabled_logger.log_file_operation(
            "read", "/etc/passwd", blocked=True, reason="Path outside project"
        )

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "file_blocked"
        assert log_entry["outcome"] == "blocked"
        assert log_entry["details"]["reason"] == "Path outside project"


class TestLogSession:
    """Tests for session logging methods."""

    def test_log_session_start(self, enabled_logger: AuditLogger) -> None:
        """Log session start with metadata."""
        enabled_logger.log_session_start(
            session_id="abc123", project="canopy", provider="bedrock"
        )

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "session_start"
        assert log_entry["outcome"] == "started"
        assert log_entry["details"]["session_id"] == "abc123"
        assert log_entry["details"]["project"] == "canopy"
        assert log_entry["details"]["provider"] == "bedrock"

    def test_log_session_end(self, enabled_logger: AuditLogger) -> None:
        """Log session end."""
        enabled_logger.log_session_end(session_id="abc123", reason="completed")

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["event_type"] == "session_end"
        assert log_entry["outcome"] == "completed"
        assert log_entry["details"]["session_id"] == "abc123"


class TestSanitizeInput:
    """Tests for input sanitization."""

    def test_redact_sensitive_keys(self, enabled_logger: AuditLogger) -> None:
        """Sensitive keys should be redacted."""
        enabled_logger._log_event(
            AuditEventType.BASH_COMMAND,
            "Bash",
            {"command": "echo", "api_key": "secret123", "password": "hunter2"},
            "success",
        )

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert log_entry["input"]["api_key"] == "[REDACTED]"
        assert log_entry["input"]["password"] == "[REDACTED]"
        assert log_entry["input"]["command"] == "echo"

    def test_truncate_long_values(self, enabled_logger: AuditLogger) -> None:
        """Long values should be truncated."""
        long_command = "x" * 2000
        enabled_logger.log_bash_command(long_command)

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        assert len(log_entry["input"]["command"]) < 2000
        assert "[truncated]" in log_entry["input"]["command"]


class TestJsonlFormat:
    """Tests for JSONL format compliance."""

    def test_multiple_entries_one_per_line(self, enabled_logger: AuditLogger) -> None:
        """Each log entry should be on its own line."""
        enabled_logger.log_bash_command("ls")
        enabled_logger.log_bash_command("pwd")
        enabled_logger.log_bash_command("echo hello")

        with open(enabled_logger.log_path) as f:
            lines = f.readlines()

        assert len(lines) == 3
        for line in lines:
            # Each line should be valid JSON
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "event_type" in entry

    def test_timestamp_iso_format(self, enabled_logger: AuditLogger) -> None:
        """Timestamps should be in ISO 8601 format."""
        enabled_logger.log_bash_command("ls")

        with open(enabled_logger.log_path) as f:
            log_entry = json.loads(f.readline())

        timestamp = log_entry["timestamp"]
        # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp


class TestGlobalLogger:
    """Tests for global logger management."""

    def test_get_audit_logger_returns_instance(self) -> None:
        """get_audit_logger should return an AuditLogger instance."""
        logger = get_audit_logger()
        assert isinstance(logger, AuditLogger)

    def test_init_audit_logger_creates_enabled(self, audit_dir: Path) -> None:
        """init_audit_logger should create an enabled logger."""
        logger = init_audit_logger(log_dir=audit_dir, enabled=True)
        assert logger.enabled is True
        logger.close()

    def test_init_audit_logger_returns_same_instance(self, audit_dir: Path) -> None:
        """After init, get_audit_logger should return the initialized instance."""
        initialized = init_audit_logger(log_dir=audit_dir, enabled=True)
        retrieved = get_audit_logger()
        assert initialized is retrieved
        initialized.close()
