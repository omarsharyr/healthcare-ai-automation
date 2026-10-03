"""Dashboard reads only FastAPI. Bounded retries are restricted to idempotent GETs."""
import time
from uuid import uuid4

import httpx


class AnalyticsUnavailable(Exception):
    pass


def get_json(base_url: str, path: str, params: dict | None = None,
             transport: httpx.BaseTransport | None = None) -> dict:
    if path not in ('/api/v1/analytics/summary', '/api/v1/analytics/activity', '/ready'):
        raise AnalyticsUnavailable('Unsupported dashboard operation')
    trace = str(uuid4())
    with httpx.Client(timeout=5, transport=transport, trust_env=False, follow_redirects=False) as client:
        for attempt in range(3):
            try:
                response = client.get(base_url.rstrip('/') + path, params=params,
                                      headers={'X-Correlation-ID': trace})
                if response.status_code in (429, 502, 503, 504):
                    if attempt < 2:
                        time.sleep(0.25 * (2 ** attempt))
                        continue
                    raise AnalyticsUnavailable('API temporarily unavailable')
                if response.status_code != 200:
                    raise AnalyticsUnavailable('API rejected the dashboard request')
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError()
                return result
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                raise AnalyticsUnavailable('API connection unavailable') from None
            except (ValueError, httpx.HTTPError):
                raise AnalyticsUnavailable('Unexpected API response') from None
    raise AnalyticsUnavailable('API unavailable')
