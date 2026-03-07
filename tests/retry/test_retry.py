"""Tests for retry_with_backoff decorator.

All tests patch time.sleep to avoid real delays.
"""

import os
import sys
from unittest.mock import patch, MagicMock, call

import pytest

# Ensure project root is on the path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.retry import retry_with_backoff


# ---------------------------------------------------------------------------
# Test functions decorated with retry
# ---------------------------------------------------------------------------


class TestRetrySucceedsFirstTry:
    """Function succeeds on the first call — no retries needed."""

    @patch('scripts.utils.retry.time.sleep')
    def test_succeeds_first_try(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def succeed():
            nonlocal call_count
            call_count += 1
            return 'ok'

        result = succeed()
        assert result == 'ok'
        assert call_count == 1
        mock_sleep.assert_not_called()


class TestRetryAfterTransientFailure:
    """Function fails once with a transient error, then succeeds."""

    @patch('scripts.utils.retry.time.sleep')
    def test_succeeds_after_transient_failure(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError('connection reset')
            return 'recovered'

        result = flaky()
        assert result == 'recovered'
        assert call_count == 2
        assert mock_sleep.call_count == 1
        # First retry delay: base_delay * 2^0 + jitter = ~2-3s
        delay = mock_sleep.call_args[0][0]
        assert 2.0 <= delay <= 3.0


class TestRetryExhaustsRetries:
    """Function fails on every attempt — raises after all retries."""

    @patch('scripts.utils.retry.time.sleep')
    def test_exhausts_retries(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f'failure #{call_count}')

        with pytest.raises(ConnectionError, match='failure #4'):
            always_fail()

        # 1 initial + 3 retries = 4 total calls
        assert call_count == 4
        # 3 sleeps (between attempts 1-2, 2-3, 3-4)
        assert mock_sleep.call_count == 3

        # Verify exponential backoff delays (ignoring jitter)
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert 2.0 <= delays[0] <= 3.0   # 2 * 2^0 + jitter
        assert 4.0 <= delays[1] <= 5.0   # 2 * 2^1 + jitter
        assert 8.0 <= delays[2] <= 9.0   # 2 * 2^2 + jitter


class TestNoRetryOnPermanentError:
    """Non-retryable errors fail immediately without sleeping."""

    @patch('scripts.utils.retry.time.sleep')
    def test_no_retry_on_permanent_error(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def bad_request():
            nonlocal call_count
            call_count += 1
            raise ValueError('invalid input')

        with pytest.raises(ValueError, match='invalid input'):
            bad_request()

        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch('scripts.utils.retry.time.sleep')
    def test_no_retry_on_http_400(self, mock_sleep):
        """Google API 400 (bad request) should not be retried."""
        from googleapiclient.errors import HttpError
        import httplib2

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def bad_api_call():
            nonlocal call_count
            call_count += 1
            resp = httplib2.Response({'status': 400})
            raise HttpError(resp, b'bad request')

        with pytest.raises(HttpError):
            bad_api_call()

        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch('scripts.utils.retry.time.sleep')
    def test_no_retry_on_http_404(self, mock_sleep):
        """Google API 404 (not found) should not be retried."""
        from googleapiclient.errors import HttpError
        import httplib2

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def not_found():
            nonlocal call_count
            call_count += 1
            resp = httplib2.Response({'status': 404})
            raise HttpError(resp, b'not found')

        with pytest.raises(HttpError):
            not_found()

        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch('scripts.utils.retry.time.sleep')
    def test_retries_on_http_429(self, mock_sleep):
        """Google API 429 (rate limit) SHOULD be retried."""
        from googleapiclient.errors import HttpError
        import httplib2

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def rate_limited():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                resp = httplib2.Response({'status': 429})
                raise HttpError(resp, b'rate limited')
            return 'ok'

        result = rate_limited()
        assert result == 'ok'
        assert call_count == 2
        assert mock_sleep.call_count == 1

    @patch('scripts.utils.retry.time.sleep')
    def test_retries_on_http_503(self, mock_sleep):
        """Google API 503 (service unavailable) SHOULD be retried."""
        from googleapiclient.errors import HttpError
        import httplib2

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=2)
        def service_unavailable():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                resp = httplib2.Response({'status': 503})
                raise HttpError(resp, b'service unavailable')
            return 'ok'

        result = service_unavailable()
        assert result == 'ok'
        assert call_count == 2
