"""Reproducible synthetic end-to-end demo; only permitted with the fake provider.

Run from the repository root after publishing the n8n workflows. Creates a new
synthetic request and resolves its review; never truncates application data.
"""
import argparse
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--decision', choices=['approve', 'reject'], default='approve')
    parser.add_argument('--api', default='http://localhost:8000')
    parser.add_argument('--n8n', default='http://localhost:5678')
    args = parser.parse_args()
    subprocess.run(['docker', 'compose', 'exec', '-T', 'backend', 'python', '-c',
                    "from app.core.ai_config import get_ai_settings; assert get_ai_settings().ai_provider == 'fake', 'Use AI_PROVIDER=fake for this reproducible demo'"],
                   cwd=ROOT, check=True, capture_output=True)
    trace = str(uuid4())

    def call(url: str, body: dict | None = None) -> tuple[dict, int, str | None]:
        request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json', 'X-Correlation-ID': trace})
        try:
            response = urlopen(request, timeout=50)
        except HTTPError as error:
            response = error
        with response:
            return json.load(response), response.status, response.headers.get('X-Correlation-ID')

    before, code, _ = call(args.api + '/api/v1/analytics/summary')
    assert code == 200
    payload = json.loads((ROOT / 'sample-data/demo-low-confidence.json').read_text())
    result, code, returned_trace = call(args.n8n + '/webhook/healthcare-request-automation', payload)
    assert code == 200 and returned_trace == trace
    assert result['confidence'] == .6 and result['ai_recommendation'] == 'AUTO_PROCESS'
    assert result['system_decision'] == 'HUMAN_REVIEW' and result['decision_reason'] == 'Confidence below 0.85.'
    review_id, request_uuid = result['review_id'], result['request_uuid']
    reviewed, code, _ = call(f'{args.api}/api/v1/reviews/{review_id}/{args.decision}', {'reviewer_notes':'Synthetic portfolio demo reviewed.'})
    assert code == 200 and reviewed['status'] == ('APPROVED' if args.decision == 'approve' else 'REJECTED')
    assert call(f'{args.api}/api/v1/reviews/{review_id}/{args.decision}', {})[1] == 409
    agent, code, _ = call(args.n8n + '/webhook/healthcare-agent-operations',
                         {'message':'Check status and history', 'request_uuid':request_uuid})
    assert code == 200 and agent['tools_used'] == ['get_request_status', 'get_request_history']
    assert not agent['escalated']
    activity, code, _ = call(args.api + '/api/v1/analytics/activity?limit=100')
    types = {item['event_type'] for item in activity['items'] if item['correlation_id'] == trace}
    assert {'REQUEST_RECEIVED','PHI_REDACTION_COMPLETED','AI_CLASSIFICATION_COMPLETED',
            'WORKFLOW_DECISION_MADE','HUMAN_REVIEW_COMPLETED','AGENT_TOOL_EXECUTED'}.issubset(types)
    after, code, _ = call(args.api + '/api/v1/analytics/summary')
    assert after['total_requests'] == before['total_requests'] + 1
    assert after['automated'] == before['automated']  # human approval never counts as automation
    print(json.dumps({'result':'PASS','provider':'fake','request_uuid':request_uuid,'correlation_id':trace,
                      'confidence':result['confidence'],'ai_recommendation':result['ai_recommendation'],
                      'system_decision_before_review':result['system_decision'],'review_status':reviewed['status'],
                      'tools_used':agent['tools_used'],'next':'Refresh http://localhost:8501'}, indent=2))


if __name__ == '__main__':
    main()
