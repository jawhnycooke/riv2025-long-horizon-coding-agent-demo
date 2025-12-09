"""Tests for src/tracing.py - OpenTelemetry tracing utilities."""

import pytest

from src.config import TracingSettings
from src.tracing import (
    NoOpSpan,
    TracingManager,
    get_tracing_manager,
    initialize_tracing,
)


class TestTracingSettings:
    """Tests for TracingSettings dataclass."""

    def test_default_values(self) -> None:
        """TracingSettings has correct default values."""
        settings = TracingSettings()
        assert settings.enabled is False
        assert settings.service_name == "claude-code-agent"
        assert settings.exporter == "console"
        assert settings.otlp_endpoint is None

    def test_from_dict_all_values(self) -> None:
        """TracingSettings.from_dict parses all fields."""
        data = {
            "enabled": True,
            "service_name": "my-service",
            "exporter": "otlp",
            "otlp_endpoint": "http://localhost:4317",
        }
        settings = TracingSettings.from_dict(data)
        assert settings.enabled is True
        assert settings.service_name == "my-service"
        assert settings.exporter == "otlp"
        assert settings.otlp_endpoint == "http://localhost:4317"

    def test_from_dict_defaults(self) -> None:
        """TracingSettings.from_dict uses defaults for missing values."""
        settings = TracingSettings.from_dict({})
        assert settings.enabled is False
        assert settings.service_name == "claude-code-agent"
        assert settings.exporter == "console"

    def test_to_dict(self) -> None:
        """TracingSettings.to_dict produces correct output."""
        settings = TracingSettings(
            enabled=True,
            service_name="test-service",
            exporter="otlp",
            otlp_endpoint="http://localhost:4317",
        )
        result = settings.to_dict()
        assert result == {
            "enabled": True,
            "service_name": "test-service",
            "exporter": "otlp",
            "otlp_endpoint": "http://localhost:4317",
        }

    def test_to_dict_without_endpoint(self) -> None:
        """TracingSettings.to_dict omits null endpoint."""
        settings = TracingSettings(enabled=True)
        result = settings.to_dict()
        assert "otlp_endpoint" not in result


class TestTracingManager:
    """Tests for TracingManager class."""

    def test_default_disabled(self) -> None:
        """TracingManager is disabled by default."""
        manager = TracingManager()
        assert manager.is_enabled is False

    def test_enabled_via_settings(self) -> None:
        """TracingManager respects enabled setting."""
        settings = TracingSettings(enabled=True)
        manager = TracingManager(settings)
        # Note: is_enabled depends on OTEL being available
        # but _enabled should be True
        assert manager._enabled is True

    def test_env_var_override_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OTEL_TRACING_ENABLED=true enables tracing."""
        monkeypatch.setenv("OTEL_TRACING_ENABLED", "true")
        settings = TracingSettings(enabled=False)
        manager = TracingManager(settings)
        assert manager._enabled is True

    def test_env_var_override_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OTEL_TRACING_ENABLED=false disables tracing."""
        monkeypatch.setenv("OTEL_TRACING_ENABLED", "false")
        settings = TracingSettings(enabled=True)
        manager = TracingManager(settings)
        assert manager._enabled is False

    def test_env_var_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Various env var values are interpreted correctly."""
        for value in ["true", "1", "yes"]:
            monkeypatch.setenv("OTEL_TRACING_ENABLED", value)
            manager = TracingManager()
            assert manager._enabled is True, f"Failed for value: {value}"

        for value in ["false", "0", "no"]:
            monkeypatch.setenv("OTEL_TRACING_ENABLED", value)
            manager = TracingManager()
            assert manager._enabled is False, f"Failed for value: {value}"

    def test_is_available_reflects_import(self) -> None:
        """is_available reflects whether OpenTelemetry is installed."""
        manager = TracingManager()
        # This should return True since OTel is in requirements
        assert manager.is_available is True

    def test_span_returns_noop_when_disabled(self) -> None:
        """span() returns NoOpSpan when tracing is disabled."""
        manager = TracingManager(TracingSettings(enabled=False))
        with manager.span("test_span", key="value") as span:
            assert isinstance(span, NoOpSpan)

    def test_initialize_returns_false_when_disabled(self) -> None:
        """initialize() returns False when tracing is disabled."""
        manager = TracingManager(TracingSettings(enabled=False))
        result = manager.initialize()
        assert result is False

    def test_initialize_with_console_exporter(self) -> None:
        """initialize() configures console exporter."""
        settings = TracingSettings(enabled=True, exporter="console")
        manager = TracingManager(settings)
        result = manager.initialize()
        assert result is True
        assert manager._initialized is True

    def test_initialize_idempotent(self) -> None:
        """initialize() is idempotent."""
        settings = TracingSettings(enabled=True)
        manager = TracingManager(settings)
        result1 = manager.initialize()
        result2 = manager.initialize()
        assert result1 is True
        assert result2 is True


class TestNoOpSpan:
    """Tests for NoOpSpan class."""

    def test_set_attribute_no_error(self) -> None:
        """set_attribute doesn't raise."""
        span = NoOpSpan()
        span.set_attribute("key", "value")  # Should not raise

    def test_set_status_no_error(self) -> None:
        """set_status doesn't raise."""
        span = NoOpSpan()
        span.set_status(None, "description")  # Should not raise

    def test_record_exception_no_error(self) -> None:
        """record_exception doesn't raise."""
        span = NoOpSpan()
        span.record_exception(ValueError("test"))  # Should not raise

    def test_add_event_no_error(self) -> None:
        """add_event doesn't raise."""
        span = NoOpSpan()
        span.add_event("event", {"key": "value"})  # Should not raise


class TestToolCallTracer:
    """Tests for ToolCallTracer class."""

    def test_context_manager_with_disabled_tracing(self) -> None:
        """ToolCallTracer works as context manager when tracing disabled."""
        manager = TracingManager(TracingSettings(enabled=False))
        with manager.trace_tool_call("test_tool", {"input": "data"}) as tracer:
            tracer.set_success("result")
            # Should not raise

    def test_context_manager_with_enabled_tracing(self) -> None:
        """ToolCallTracer works as context manager when tracing enabled."""
        settings = TracingSettings(enabled=True, exporter="none")
        manager = TracingManager(settings)
        manager.initialize()

        with manager.trace_tool_call("test_tool", {"input": "data"}) as tracer:
            tracer.add_attribute("custom", "value")
            tracer.set_success("result")

    def test_set_error(self) -> None:
        """set_error sets error status."""
        settings = TracingSettings(enabled=True, exporter="none")
        manager = TracingManager(settings)
        manager.initialize()

        with manager.trace_tool_call("failing_tool") as tracer:
            tracer.set_error("Something went wrong")


class TestGlobalFunctions:
    """Tests for module-level functions."""

    def test_get_tracing_manager_singleton(self) -> None:
        """get_tracing_manager returns singleton."""
        # Clear any existing global manager
        import src.tracing as tracing_module

        tracing_module._global_tracing = None

        manager1 = get_tracing_manager()
        manager2 = get_tracing_manager()
        assert manager1 is manager2

    def test_initialize_tracing_with_settings(self) -> None:
        """initialize_tracing accepts settings."""
        import src.tracing as tracing_module

        tracing_module._global_tracing = None

        settings = TracingSettings(enabled=True, service_name="test-init")
        result = initialize_tracing(settings)
        assert result is True

    def test_initialize_tracing_without_settings(self) -> None:
        """initialize_tracing works without settings (disabled)."""
        import src.tracing as tracing_module

        tracing_module._global_tracing = None

        result = initialize_tracing(None)
        assert result is False  # Disabled by default


class TestConfigIntegration:
    """Tests for TracingSettings integration with ProjectConfig."""

    def test_project_config_includes_tracing(self) -> None:
        """ProjectConfig includes tracing settings."""
        from src.config import ProjectConfig, Provider

        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model="test-model",
            tracing=TracingSettings(enabled=True, exporter="otlp"),
        )
        assert config.tracing is not None
        assert config.tracing.enabled is True
        assert config.tracing.exporter == "otlp"

    def test_project_config_from_dict_with_tracing(self) -> None:
        """ProjectConfig.from_dict parses tracing section."""
        from src.config import ProjectConfig

        data = {
            "provider": "anthropic",
            "model": "test-model",
            "tracing": {
                "enabled": True,
                "service_name": "my-agent",
                "exporter": "console",
            },
        }
        config = ProjectConfig.from_dict(data)
        assert config.tracing is not None
        assert config.tracing.enabled is True
        assert config.tracing.service_name == "my-agent"

    def test_project_config_to_dict_with_tracing(self) -> None:
        """ProjectConfig.to_dict includes tracing section."""
        from src.config import ProjectConfig, Provider

        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model="test-model",
            tracing=TracingSettings(enabled=True),
        )
        result = config.to_dict()
        assert "tracing" in result
        assert result["tracing"]["enabled"] is True
