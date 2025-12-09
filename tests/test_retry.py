"""Tests for src/retry.py - Retry logic with exponential backoff."""

import time

import pytest

from src.retry import (
    PERMANENT_STATUS_CODES,
    TRANSIENT_STATUS_CODES,
    PermanentError,
    RetryableError,
    RetryConfig,
    calculate_delay,
    get_default_retry_config,
    init_retry_config,
    is_transient_error,
    set_default_retry_config,
    with_async_retry,
    with_retry,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """Default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_values(self) -> None:
        """Custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.jitter is False


class TestStatusCodes:
    """Tests for HTTP status code classification."""

    def test_transient_status_codes(self) -> None:
        """Transient status codes are defined."""
        expected = {429, 500, 502, 503, 504}
        assert expected == TRANSIENT_STATUS_CODES

    def test_permanent_status_codes(self) -> None:
        """Permanent status codes are defined."""
        expected = {400, 401, 403, 404, 405, 409, 422}
        assert expected == PERMANENT_STATUS_CODES

    def test_no_overlap(self) -> None:
        """Transient and permanent codes don't overlap."""
        assert TRANSIENT_STATUS_CODES.isdisjoint(PERMANENT_STATUS_CODES)


class TestCustomExceptions:
    """Tests for RetryableError and PermanentError."""

    def test_retryable_error(self) -> None:
        """RetryableError stores status code and original error."""
        original = ValueError("original error")
        error = RetryableError("retry this", status_code=429, original_error=original)
        assert str(error) == "retry this"
        assert error.status_code == 429
        assert error.original_error is original

    def test_permanent_error(self) -> None:
        """PermanentError stores status code and original error."""
        original = ValueError("original error")
        error = PermanentError("don't retry", status_code=400, original_error=original)
        assert str(error) == "don't retry"
        assert error.status_code == 400
        assert error.original_error is original


class TestIsTransientError:
    """Tests for is_transient_error function."""

    def test_retryable_error_is_transient(self) -> None:
        """RetryableError is always transient."""
        error = RetryableError("retry this")
        assert is_transient_error(error) is True

    def test_permanent_error_not_transient(self) -> None:
        """PermanentError is never transient."""
        error = PermanentError("don't retry")
        assert is_transient_error(error) is False

    def test_status_code_429_is_transient(self) -> None:
        """429 rate limit is transient."""

        class MockError(Exception):
            status_code = 429

        assert is_transient_error(MockError()) is True

    def test_status_code_503_is_transient(self) -> None:
        """503 service unavailable is transient."""

        class MockError(Exception):
            status_code = 503

        assert is_transient_error(MockError()) is True

    def test_status_code_400_not_transient(self) -> None:
        """400 bad request is not transient."""

        class MockError(Exception):
            status_code = 400

        assert is_transient_error(MockError()) is False

    def test_status_code_401_not_transient(self) -> None:
        """401 unauthorized is not transient."""

        class MockError(Exception):
            status_code = 401

        assert is_transient_error(MockError()) is False

    def test_connection_error_is_transient(self) -> None:
        """ConnectionError is transient."""
        assert is_transient_error(ConnectionError()) is True

    def test_timeout_error_is_transient(self) -> None:
        """TimeoutError is transient."""
        assert is_transient_error(TimeoutError()) is True

    def test_os_error_is_transient(self) -> None:
        """OSError (network issues) is transient."""
        assert is_transient_error(OSError()) is True

    def test_timeout_in_message_is_transient(self) -> None:
        """Error message containing 'timeout' is transient."""
        assert is_transient_error(Exception("connection timeout")) is True

    def test_rate_limit_in_message_is_transient(self) -> None:
        """Error message containing 'rate limit' is transient."""
        assert is_transient_error(Exception("rate limit exceeded")) is True

    def test_unknown_error_not_transient(self) -> None:
        """Unknown errors default to non-transient (fail fast)."""
        assert is_transient_error(ValueError("unknown error")) is False


class TestCalculateDelay:
    """Tests for calculate_delay function."""

    def test_first_attempt_base_delay(self) -> None:
        """First attempt uses base delay."""
        config = RetryConfig(base_delay=1.0, jitter=False)
        delay = calculate_delay(0, config)
        assert delay == 1.0

    def test_exponential_backoff(self) -> None:
        """Delay increases exponentially."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert calculate_delay(0, config) == 1.0
        assert calculate_delay(1, config) == 2.0
        assert calculate_delay(2, config) == 4.0
        assert calculate_delay(3, config) == 8.0

    def test_max_delay_cap(self) -> None:
        """Delay is capped at max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)
        assert calculate_delay(10, config) == 5.0  # Would be 1024 without cap

    def test_jitter_adds_randomness(self) -> None:
        """Jitter adds randomness to delay."""
        config = RetryConfig(base_delay=1.0, jitter=True)

        # With jitter, delay should vary (run multiple times to check)
        delays = [calculate_delay(0, config) for _ in range(10)]
        # Not all delays should be identical
        assert len(set(delays)) > 1

    def test_jitter_range(self) -> None:
        """Jitter keeps delay within expected range."""
        config = RetryConfig(base_delay=2.0, jitter=True)

        for _ in range(100):
            delay = calculate_delay(0, config)
            # With 0.5 + random(), range is [1.0, 4.0) (0.5*2 to 1.5*2)
            assert 1.0 <= delay < 4.0


class TestWithRetry:
    """Tests for with_retry decorator."""

    def test_success_no_retry(self) -> None:
        """Successful call returns without retry."""
        call_count = 0

        @with_retry()
        def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeed()
        assert result == "success"
        assert call_count == 1

    def test_transient_error_retries(self) -> None:
        """Transient errors trigger retries."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("transient")
            return "success"

        result = fail_then_succeed()
        assert result == "success"
        assert call_count == 3

    def test_permanent_error_no_retry(self) -> None:
        """Permanent errors fail immediately."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=3, base_delay=0.01))
        def permanent_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise PermanentError("permanent")

        with pytest.raises(PermanentError):
            permanent_fail()
        assert call_count == 1  # Only called once

    def test_max_retries_exceeded(self) -> None:
        """Raises after max retries exceeded."""
        call_count = 0

        @with_retry(RetryConfig(max_retries=2, base_delay=0.01))
        def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableError("always fails")

        with pytest.raises(RetryableError):
            always_fail()
        assert call_count == 3  # Initial + 2 retries

    def test_preserves_function_metadata(self) -> None:
        """Decorator preserves function name and docstring."""

        @with_retry()
        def my_function() -> None:
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_delay_between_retries(self) -> None:
        """Retries have delay between them."""
        call_times: list[float] = []

        @with_retry(RetryConfig(max_retries=2, base_delay=0.1, jitter=False))
        def fail_with_timing() -> str:
            call_times.append(time.time())
            if len(call_times) < 3:
                raise RetryableError("retry")
            return "success"

        fail_with_timing()

        # Check delays between calls
        assert len(call_times) == 3
        first_delay = call_times[1] - call_times[0]
        assert first_delay >= 0.09  # Allow small timing variance


class TestWithAsyncRetry:
    """Tests for with_async_retry decorator."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self) -> None:
        """Successful async call returns without retry."""
        call_count = 0

        @with_async_retry()
        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await succeed()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_transient_error_retries(self) -> None:
        """Transient errors trigger async retries."""
        call_count = 0

        @with_async_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("transient")
            return "success"

        result = await fail_then_succeed()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self) -> None:
        """Permanent errors fail immediately in async."""
        call_count = 0

        @with_async_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def permanent_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise PermanentError("permanent")

        with pytest.raises(PermanentError):
            await permanent_fail()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self) -> None:
        """Raises after max retries exceeded in async."""
        call_count = 0

        @with_async_retry(RetryConfig(max_retries=2, base_delay=0.01))
        async def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableError("always fails")

        with pytest.raises(RetryableError):
            await always_fail()
        assert call_count == 3


class TestGlobalConfig:
    """Tests for global retry configuration."""

    def test_get_default_config(self) -> None:
        """get_default_retry_config returns RetryConfig."""
        config = get_default_retry_config()
        assert isinstance(config, RetryConfig)

    def test_set_default_config(self) -> None:
        """set_default_retry_config updates global config."""
        original = get_default_retry_config()
        new_config = RetryConfig(max_retries=10)

        try:
            set_default_retry_config(new_config)
            assert get_default_retry_config() is new_config
        finally:
            set_default_retry_config(original)

    def test_init_retry_config(self) -> None:
        """init_retry_config creates and sets config."""
        original = get_default_retry_config()

        try:
            config = init_retry_config(max_retries=5, base_delay=2.0, max_delay=120.0)
            assert config.max_retries == 5
            assert config.base_delay == 2.0
            assert config.max_delay == 120.0
            assert get_default_retry_config() is config
        finally:
            set_default_retry_config(original)


class TestRetrySettingsConfig:
    """Tests for RetrySettings in config.py."""

    def test_retry_settings_from_dict(self) -> None:
        """RetrySettings.from_dict parses config."""
        from src.config import RetrySettings

        data = {"max_retries": 5, "base_delay": 0.5, "max_delay": 30.0}
        settings = RetrySettings.from_dict(data)
        assert settings.max_retries == 5
        assert settings.base_delay == 0.5
        assert settings.max_delay == 30.0

    def test_retry_settings_defaults(self) -> None:
        """RetrySettings.from_dict uses defaults."""
        from src.config import RetrySettings

        settings = RetrySettings.from_dict({})
        assert settings.max_retries == 3
        assert settings.base_delay == 1.0
        assert settings.max_delay == 60.0

    def test_retry_settings_to_dict(self) -> None:
        """RetrySettings.to_dict serializes correctly."""
        from src.config import RetrySettings

        settings = RetrySettings(max_retries=5, base_delay=0.5, max_delay=30.0)
        data = settings.to_dict()
        assert data == {"max_retries": 5, "base_delay": 0.5, "max_delay": 30.0}

    def test_project_config_with_retry(self) -> None:
        """ProjectConfig parses retry settings."""
        from src.config import ProjectConfig

        data = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "retry": {"max_retries": 5, "base_delay": 2.0, "max_delay": 120.0},
        }
        config = ProjectConfig.from_dict(data)
        assert config.retry is not None
        assert config.retry.max_retries == 5
        assert config.retry.base_delay == 2.0
        assert config.retry.max_delay == 120.0

    def test_project_config_without_retry(self) -> None:
        """ProjectConfig works without retry settings."""
        from src.config import ProjectConfig

        data = {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"}
        config = ProjectConfig.from_dict(data)
        assert config.retry is None

    def test_project_config_to_dict_with_retry(self) -> None:
        """ProjectConfig.to_dict includes retry when set."""
        from src.config import ProjectConfig, Provider, RetrySettings

        config = ProjectConfig(
            provider=Provider.ANTHROPIC,
            model="claude-sonnet-4-5-20250929",
            retry=RetrySettings(max_retries=5),
        )
        data = config.to_dict()
        assert "retry" in data
        assert data["retry"]["max_retries"] == 5
