"""OpenTelemetry tracing utilities for Claude Code.

Provides distributed tracing for tool calls using OpenTelemetry.
Tracing can be enabled via config or OTEL_TRACING_ENABLED env var.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .config import TracingSettings

# Try to import OpenTelemetry, gracefully handle if not available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.trace import Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]


class TracingManager:
    """Manages OpenTelemetry tracing configuration and span creation.

    Usage:
        tracing = TracingManager(settings)
        tracing.initialize()

        with tracing.span("tool_call", tool_name="bash", command="npm test") as span:
            result = execute_tool()
            if result.error:
                span.set_status(StatusCode.ERROR, result.error)
    """

    def __init__(self, settings: TracingSettings | None = None) -> None:
        """Initialize the tracing manager.

        Args:
            settings: TracingSettings from config, or None to use defaults
        """
        self._settings = settings
        self._tracer: Any = None
        self._initialized = False
        self._enabled = self._determine_enabled()

    def _determine_enabled(self) -> bool:
        """Determine if tracing should be enabled.

        Priority:
        1. OTEL_TRACING_ENABLED env var (explicit override)
        2. Settings from config
        3. Default: disabled
        """
        env_enabled = os.environ.get("OTEL_TRACING_ENABLED", "").lower()
        if env_enabled in ("true", "1", "yes"):
            return True
        if env_enabled in ("false", "0", "no"):
            return False
        if self._settings:
            return self._settings.enabled
        return False

    @property
    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._enabled and OTEL_AVAILABLE

    @property
    def is_available(self) -> bool:
        """Check if OpenTelemetry is available."""
        return OTEL_AVAILABLE

    def initialize(self) -> bool:
        """Initialize the OpenTelemetry tracer.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            return True

        if not OTEL_AVAILABLE:
            print("OpenTelemetry not available - tracing disabled")
            return False

        if not self._enabled:
            return False

        try:
            # Get service name
            service_name = (
                self._settings.service_name if self._settings else "claude-code-agent"
            )

            # Create resource with service name
            resource = Resource(attributes={SERVICE_NAME: service_name})

            # Create tracer provider
            provider = TracerProvider(resource=resource)

            # Configure exporter based on settings
            exporter_type = self._settings.exporter if self._settings else "console"

            if exporter_type == "console":
                processor = SimpleSpanProcessor(ConsoleSpanExporter())
                provider.add_span_processor(processor)
            elif exporter_type == "otlp":
                # OTLP exporter requires additional package
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )

                    endpoint = (
                        self._settings.otlp_endpoint
                        if self._settings and self._settings.otlp_endpoint
                        else os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                    )
                    exporter = OTLPSpanExporter(endpoint=endpoint)
                    processor = BatchSpanProcessor(exporter)
                    provider.add_span_processor(processor)
                except ImportError:
                    print("OTLP exporter not available, falling back to console")
                    processor = SimpleSpanProcessor(ConsoleSpanExporter())
                    provider.add_span_processor(processor)
            # "none" exporter means no span output (just in-memory tracing)

            # Set global tracer provider
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(__name__)
            self._initialized = True

            print(f"OpenTelemetry tracing initialized (exporter: {exporter_type})")
            return True

        except Exception as e:
            print(f"Failed to initialize OpenTelemetry tracing: {e}")
            return False

    @contextmanager
    def span(
        self,
        name: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """Create a traced span for an operation.

        Args:
            name: Name of the span (e.g., "tool_call", "api_request")
            **attributes: Attributes to add to the span

        Yields:
            The span object (or a no-op object if tracing is disabled)
        """
        if not self.is_enabled or not self._initialized or self._tracer is None:
            # Return a no-op span that supports the same interface
            yield NoOpSpan()
            return

        with self._tracer.start_as_current_span(name) as span:
            # Set attributes
            for key, value in attributes.items():
                if value is not None:
                    # Convert to string if not a basic type
                    if isinstance(value, (str, int, float, bool)):
                        span.set_attribute(key, value)
                    else:
                        span.set_attribute(key, str(value))
            yield span

    def trace_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
    ) -> ToolCallTracer:
        """Create a tracer for a tool call.

        Args:
            tool_name: Name of the tool being called
            tool_input: Input parameters to the tool

        Returns:
            ToolCallTracer context manager
        """
        return ToolCallTracer(self, tool_name, tool_input)


class NoOpSpan:
    """No-op span implementation for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op set_attribute."""
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        """No-op set_status."""
        pass

    def record_exception(self, exception: BaseException) -> None:
        """No-op record_exception."""
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op add_event."""
        pass


class ToolCallTracer:
    """Context manager for tracing tool calls with timing and status.

    Usage:
        with tracing.trace_tool_call("bash", {"command": "npm test"}) as tracer:
            result = execute_bash(command)
            if result.error:
                tracer.set_error(result.error)
            tracer.set_success()
    """

    def __init__(
        self,
        manager: TracingManager,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the tool call tracer.

        Args:
            manager: The TracingManager instance
            tool_name: Name of the tool
            tool_input: Input parameters
        """
        self._manager = manager
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._span: Any = None
        self._start_time: float = 0

    def __enter__(self) -> ToolCallTracer:
        """Enter the context manager and start the span."""
        self._start_time = time.time()

        # Prepare attributes
        attrs: dict[str, Any] = {
            "tool.name": self._tool_name,
        }

        # Add truncated input preview
        if self._tool_input:
            input_preview = str(self._tool_input)[:500]
            attrs["tool.input_preview"] = input_preview

        # Start span using manager's span context manager
        self._span_cm = self._manager.span(f"tool_call.{self._tool_name}", **attrs)
        self._span = self._span_cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the context manager and finalize the span."""
        duration_ms = (time.time() - self._start_time) * 1000
        self._span.set_attribute("tool.duration_ms", duration_ms)

        if exc_val is not None:
            self._span.record_exception(exc_val)
            if OTEL_AVAILABLE:
                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))

        self._span_cm.__exit__(exc_type, exc_val, exc_tb)

    def set_success(self, result_preview: str | None = None) -> None:
        """Mark the tool call as successful.

        Args:
            result_preview: Optional truncated preview of the result
        """
        if OTEL_AVAILABLE:
            self._span.set_status(Status(StatusCode.OK))
        if result_preview:
            self._span.set_attribute("tool.result_preview", result_preview[:500])

    def set_error(self, error_message: str) -> None:
        """Mark the tool call as failed.

        Args:
            error_message: Description of the error
        """
        if OTEL_AVAILABLE:
            self._span.set_status(Status(StatusCode.ERROR, error_message))
        self._span.set_attribute("tool.error", error_message[:500])

    def add_attribute(self, key: str, value: Any) -> None:
        """Add an attribute to the span.

        Args:
            key: Attribute key
            value: Attribute value
        """
        self._span.set_attribute(key, value)


# Global tracing manager instance (lazy initialization)
_global_tracing: TracingManager | None = None


def get_tracing_manager(settings: TracingSettings | None = None) -> TracingManager:
    """Get or create the global tracing manager.

    Args:
        settings: Optional TracingSettings to use for initialization

    Returns:
        The global TracingManager instance
    """
    global _global_tracing
    if _global_tracing is None:
        _global_tracing = TracingManager(settings)
    return _global_tracing


def initialize_tracing(settings: TracingSettings | None = None) -> bool:
    """Initialize global tracing with settings.

    Args:
        settings: TracingSettings from config

    Returns:
        True if tracing was initialized successfully
    """
    manager = get_tracing_manager(settings)
    return manager.initialize()
