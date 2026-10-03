import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.api_client import AnalyticsUnavailable, get_json


@pytest.mark.parametrize('error', [503, 429, 'timeout'])
def test_safe_get_retries_transient_only(error, monkeypatch):
    monkeypatch.setattr('dashboard.api_client.time.sleep', lambda _: None)
    requests = []
    def handler(request):
        requests.append(request)
        if len(requests) < 3:
            if error == 'timeout':
                raise httpx.ReadTimeout('Synthetic secret')
            return httpx.Response(error)
        return httpx.Response(200, json={'total_requests': 0})
    assert get_json('http://backend', '/api/v1/analytics/summary', transport=httpx.MockTransport(handler)) == {'total_requests': 0}
    assert len(requests) == 3 and all(r.method == 'GET' for r in requests)
    assert len({r.headers['X-Correlation-ID'] for r in requests}) == 1


@pytest.mark.parametrize('status,body', [(422, '{}'), (401, '{}'), (500, '{}'), (200, 'broken')])
def test_no_retry_validation_auth_or_malformed_response(status, body):
    attempts = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(status, text=body)
    with pytest.raises(AnalyticsUnavailable):
        get_json('http://backend', '/api/v1/analytics/summary', transport=httpx.MockTransport(handler))
    assert len(attempts) == 1


def test_retry_limit_and_path_restriction(monkeypatch):
    monkeypatch.setattr('dashboard.api_client.time.sleep', lambda _: None)
    attempts = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(503, text='private database password')
    with pytest.raises(AnalyticsUnavailable, match='API temporarily unavailable'):
        get_json('http://backend', '/ready', transport=httpx.MockTransport(handler))
    assert len(attempts) == 3
    with pytest.raises(AnalyticsUnavailable, match='Unsupported'):
        get_json('http://backend', '/api/v1/requests')
