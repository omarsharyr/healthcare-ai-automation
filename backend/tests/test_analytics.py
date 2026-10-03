from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import AuditEvent, HumanReview, Request

pytestmark = pytest.mark.integration
DAY = datetime(2026, 10, 3, tzinfo=timezone.utc)


def populate(sessions):
    specs = [('processed', 'AUTO_PROCESS', 'CLAIM_STATUS', .9),
             ('processed', 'AUTO_PROCESS', 'CLAIM_STATUS', .8),
             ('processed', 'HUMAN_REVIEW', 'MISSING_INFORMATION', .6),
             ('failed', None, None, None), ('received', None, None, None),
             ('processed', 'REJECT', 'DOCUMENT_PROCESSING', .95)]
    with sessions.begin() as session:
        rows = [Request(patient_reference='PAT-70007', request_text='Synthetic secret request text.', source='api',
                        priority='normal', status=status, system_decision=decision, category=category,
                        confidence=confidence, created_at=DAY) for status, decision, category, confidence in specs]
        session.add_all(rows)
        session.flush()
        session.add_all([
            HumanReview(request_id=rows[1].id, status='APPROVED', reviewer_decision='AUTO_PROCESS', reviewed_at=DAY),
            HumanReview(request_id=rows[2].id, status='PENDING'),
        ])
        run = str(uuid4())
        for name, request_id in [('AGENT_STARTED', None), ('AGENT_TOOL_EXECUTED', rows[0].id),
                                  ('AGENT_FAILED', None), ('AGENT_FAILED', None), ('AGENT_COMPLETED', None)]:
            session.add(AuditEvent(request_id=request_id, event_type=name, actor='agent', created_at=DAY,
                                   event_metadata={'run_uuid': run, 'tool': 'get_request_status', 'secret': 'PAT-70007'}))
        session.add(AuditEvent(request_id=None, event_type='AGENT_STARTED', actor='agent', created_at=DAY))
        session.add(AuditEvent(request_id=rows[2].id, event_type='AI_CLASSIFICATION_FAILED', actor='system', created_at=DAY))
        session.add(Request(patient_reference='PAT-70008', request_text='Synthetic previous day request.', source='api',
                            priority='normal', created_at=datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)))


def test_metrics_correct_and_manual_approvals_not_automation(db_client, db_sessions):
    populate(db_sessions)
    response = db_client.get('/api/v1/analytics/summary?date_from=2026-10-03&date_to=2026-10-03')
    assert response.status_code == 200
    data = response.json()
    assert data['total_requests'] == 6
    assert data['completed_requests'] == 3
    assert data['pending_requests'] == 2
    assert data['failures'] == 1
    assert data['automated'] == 1 and data['automation_rate'] == 16.67
    assert data['human_reviews'] == 2 and data['pending_reviews'] == 1
    assert data['average_ai_confidence'] == pytest.approx(.8125)
    assert data['requests_by_category']['UNCLASSIFIED'] == 2
    assert sum(data['requests_by_decision'].values()) == 6
    assert data['requests_by_status'] == {'received': 1, 'processed': 4, 'failed': 1}
    assert data['agent_executions'] == 2 and data['agent_failures'] == 1
    assert data['agent_tool_calls'] == 1 and data['agent_tool_usage']['get_request_status'] == 1
    assert data['ai_failures'] == 1
    assert 'PAT-70007' not in response.text and 'request_text' not in response.text


def test_category_status_filters_and_agent_run_links(db_client, db_sessions):
    populate(db_sessions)
    data = db_client.get('/api/v1/analytics/summary?category=CLAIM_STATUS&status=processed').json()
    assert data['total_requests'] == 2 and data['automation_rate'] == 50
    assert data['agent_executions'] == 1 and data['agent_failures'] == 1
    assert data['human_reviews'] == 1
    data = db_client.get('/api/v1/analytics/summary?status=failed').json()
    assert data['total_requests'] == 1 and data['average_ai_confidence'] is None
    assert data['agent_executions'] == 0


def test_empty_metrics_and_filter_validation(db_client):
    data = db_client.get('/api/v1/analytics/summary').json()
    assert data['total_requests'] == 0 and data['automation_rate'] == 0
    assert data['average_ai_confidence'] is None
    for query in ['date_from=2026-10-04&date_to=2026-10-03', 'category=private', 'status=bad',
                  'date_to=9999-12-31', 'date_from=not-a-date']:
        assert db_client.get('/api/v1/analytics/summary?' + query).status_code == 422
    assert db_client.get('/api/v1/analytics/activity?limit=101').status_code == 422


def test_activity_bounded_allowlisted_and_filterable(db_client, db_sessions):
    populate(db_sessions)
    with db_sessions.begin() as session:
        session.add(AuditEvent(event_type='PAT-70007', actor='Synthetic secret',
                               event_metadata={'run_uuid': 'PAT-70007', 'prompt': 'raw text'}, created_at=DAY))
    response = db_client.get('/api/v1/analytics/activity?limit=2')
    items = response.json()['items']
    assert len(items) == 2
    assert items[0]['event_type'] == 'OTHER_EVENT' and items[0]['actor'] == 'other'
    assert items[0]['run_uuid'] is None
    assert 'PAT-70007' not in response.text and 'raw text' not in response.text
    assert db_client.get('/api/v1/analytics/activity?date_to=2026-10-02').json()['items'] == []
    filtered = db_client.get('/api/v1/analytics/activity?category=CLAIM_STATUS').json()['items']
    assert len(filtered) == 5


def test_correlation_headers_logs_and_audits(db_client, db_sessions, synthetic_request, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='app')
    trace = str(uuid4())
    headers = {'X-Correlation-ID': trace}
    response = db_client.post('/api/v1/requests', json=synthetic_request, headers=headers)
    uuid = response.json()['request_uuid']
    assert response.headers['X-Correlation-ID'] == trace
    assert db_client.post(f'/api/v1/requests/{uuid}/process', headers=headers).headers['X-Correlation-ID'] == trace
    with db_sessions() as session:
        assert set(session.scalars(select(AuditEvent.correlation_id))) == {UUID(trace)}
    records = [r for r in caplog.records if r.msg == 'http_request_completed']
    assert all(r.correlation_id == trace for r in records)
    response = db_client.get('/health', headers={'X-Correlation-ID': 'PAT-70007'})
    assert UUID(response.headers['X-Correlation-ID']).version == 4
    assert response.headers['Cache-Control'] == 'no-store'
    assert db_client.get('/health').headers['X-Correlation-ID'] != trace


def test_validation_does_not_echo_unknown_sensitive_keys(db_client):
    response = db_client.post('/api/v1/agent/run', json={'message': 'synthetic message', 'PAT-70007': 'private'})
    assert response.status_code == 422 and 'PAT-70007' not in response.text
    assert 'X-Correlation-ID' in response.headers
