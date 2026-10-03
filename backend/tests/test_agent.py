import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select

from app.agents.provider import FakeAgentPlanner, OpenAIAgentPlanner, get_agent_planner
from app.core.agent_config import AgentSettings, get_agent_settings
from app.core.ai_config import AISettings
from app.models import AuditEvent, HumanReview, Request

pytestmark = pytest.mark.integration


def setup_request(client, payload):
    return client.post('/api/v1/requests', json=payload).json()['request_uuid']


def use_plan(client, calls, intent='lookup'):
    planner = FakeAgentPlanner(json.dumps({'intent': intent, 'calls': [
        {'name': name, 'arguments': json.dumps(args) if not isinstance(args, str) else args}
        for name, args in calls]}))
    client.app.dependency_overrides[get_agent_planner] = lambda: planner


def run(client, uuid=None, message='Check the request status'):
    return client.post('/api/v1/agent/run', json={'message': message, 'request_uuid': uuid})


def events(sessions):
    with sessions() as session:
        return list(session.scalars(select(AuditEvent.event_type).order_by(AuditEvent.id)))


def test_valid_multiple_calls_and_audit(db_client, db_sessions, synthetic_request):
    uuid = setup_request(db_client, synthetic_request)
    use_plan(db_client, [('get_request_status', {'request_uuid': uuid}),
                         ('get_request_history', {'request_uuid': uuid}),
                         ('get_required_documents', {'category': 'CLAIM_STATUS'}),
                         ('get_pending_review_count', {})])
    response = run(db_client, uuid)
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'completed' and len(body['tools_used']) == 4
    assert not body['escalated']
    assert body['results'][0]['output']['status'] == 'received'
    assert body['results'][2]['output']['synthetic_policy'] is True
    assert body['results'][3]['output']['pending_count'] == 0
    types = events(db_sessions)
    assert types.count('AGENT_TOOL_EXECUTED') == 4
    assert 'AGENT_STARTED' in types and types[-1] == 'AGENT_COMPLETED'
    assert 'PAT-10042' not in response.text


@pytest.mark.parametrize('name,args,code', [
    ('delete_database', {}, 'unknown_tool'),
    ('approve_review', {}, 'unknown_tool'),
    ('get_request_status', '{broken', 'malformed_arguments'),
    ('get_pending_review_count', {'sql': 'DROP TABLE requests'}, 'malformed_arguments'),
    ('get_request_status', {'request_uuid': str(uuid4())}, 'outside_request_scope'),
])
def test_rejects_unknown_malformed_and_scope(db_client, db_sessions, name, args, code):
    use_plan(db_client, [(name, args)])
    body = run(db_client).json()
    assert body['status'] == 'fallback' and body['tools_used'] == []
    assert body['human_action_required'] and not body['escalated']
    with db_sessions() as session:
        metadata = [e.event_metadata for e in session.scalars(select(AuditEvent))]
        assert any(m.get('reason_code') == code for m in metadata)
        assert 'DROP TABLE' not in json.dumps(metadata)


def test_scope_cannot_be_expanded_and_preflight_prevents_write(db_client, db_sessions, synthetic_request):
    first = setup_request(db_client, synthetic_request)
    second = setup_request(db_client, synthetic_request)
    use_plan(db_client, [('create_human_review', {'request_uuid': second, 'reason': 'USER_REQUESTED'}),
                         ('get_request_status', {'request_uuid': second})])
    body = run(db_client, first).json()
    assert body['status'] == 'fallback' and body['escalated']
    assert body['tools_used'] == ['create_human_review']  # trusted fallback, scoped to first
    assert db_client.get(f'/api/v1/requests/{second}').json()['system_decision'] is None


def test_human_escalation_idempotence_and_completed_protection(db_client, db_sessions, synthetic_request):
    uuid = setup_request(db_client, synthetic_request)
    use_plan(db_client, [('create_human_review', {'request_uuid': uuid, 'reason': 'USER_REQUESTED'})])
    body = run(db_client, uuid).json()
    assert body['escalated'] and body['status'] == 'completed'
    review_id = body['results'][0]['output']['review_id']
    assert not run(db_client, uuid).json()['results'][0]['output']['created']
    assert db_client.post(f'/api/v1/reviews/{review_id}/approve').status_code == 200
    assert not run(db_client, uuid).json()['escalated']
    assert db_client.get(f'/api/v1/requests/{uuid}').json()['system_decision'] == 'AUTO_PROCESS'
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 1


def test_limit_and_server_count_permission(db_client, db_sessions):
    db_client.app.dependency_overrides[get_agent_settings] = lambda: AgentSettings(max_tool_calls=1, allow_global_count=False)
    use_plan(db_client, [('get_pending_review_count', {}), ('get_pending_review_count', {})])
    assert run(db_client).json()['tools_used'] == []
    use_plan(db_client, [('get_pending_review_count', {})])
    assert run(db_client).json()['status'] == 'fallback'
    with db_sessions() as session:
        codes = [e.event_metadata.get('reason_code') for e in session.scalars(select(AuditEvent))]
        assert 'tool_limit' in codes and 'global_count_denied' in codes


@pytest.mark.parametrize('output', ['not json', '{"intent":"lookup","calls":[],"extra":true}'])
def test_malformed_plan_falls_back_to_review(db_client, synthetic_request, output):
    uuid = setup_request(db_client, synthetic_request)
    db_client.app.dependency_overrides[get_agent_planner] = lambda: FakeAgentPlanner(output)
    body = run(db_client, uuid).json()
    assert body['status'] == 'fallback' and body['escalated']


@pytest.mark.parametrize('timeout', [True, False])
def test_timeout_and_provider_failure(db_client, db_sessions, synthetic_request, timeout):
    class FailingPlanner(FakeAgentPlanner):
        async def plan(self, *args):
            if timeout:
                await asyncio.sleep(10)
            raise RuntimeError('secret PAT-10042')
    db_client.app.dependency_overrides[get_agent_planner] = lambda: FailingPlanner()
    db_client.app.dependency_overrides[get_agent_settings] = lambda: AgentSettings(timeout_seconds=0.1)
    uuid = setup_request(db_client, synthetic_request)
    response = run(db_client, uuid)
    body = response.json()
    assert body['status'] == 'fallback' and body['human_action_required']
    assert body['escalated'] is (not timeout)
    assert 'secret' not in response.text
    assert 'AGENT_FAILED' in events(db_sessions)


def test_planner_receives_redaction_only_and_no_prompt_audit(db_client, db_sessions):
    class InspectPlanner(FakeAgentPlanner):
        async def plan(self, message, scope, schemas, timeout):
            assert 'PAT-12345' not in message and '1995-10-02' not in message
            assert set(schemas) == {'get_request_status', 'get_request_history', 'get_required_documents',
                                    'create_human_review', 'get_pending_review_count'}
            return await super().plan('pending count', scope, schemas, timeout)
    db_client.app.dependency_overrides[get_agent_planner] = lambda: InspectPlanner()
    assert run(db_client, message='PAT-12345 DOB 1995-10-02 pending count').json()['status'] == 'completed'
    with db_sessions() as session:
        assert 'PAT-12345' not in json.dumps([e.event_metadata for e in session.scalars(select(AuditEvent))])


def test_uuid_in_message_and_invalid_api_input(db_client, synthetic_request):
    uuid = setup_request(db_client, synthetic_request)
    assert run(db_client, message=f'Check request {uuid}').json()['status'] == 'completed'
    assert run(db_client, message='Check request REQ-123').json()['human_action_required']
    assert run(db_client, uuid='REQ-123').status_code == 422
    assert db_client.post('/api/v1/agent/run', json={'message': 'hi'}).status_code == 422


@pytest.mark.parametrize('bad', [False, True])
def test_real_planner_wire_contract_without_paid_call(bad):
    def transport(request):
        body = json.loads(request.content)
        assert body['store'] is False and body['text']['format']['strict'] is True
        assert 'tools' not in body  # No hosted shell/code tools are enabled.
        output = [{'type': 'refusal'}] if bad else [{'type': 'output_text', 'text': '{"intent":"unsupported","calls":[]}'}]
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': output}]})
    planner = OpenAIAgentPlanner(AISettings(openai_api_key='synthetic-test-key'), httpx.MockTransport(transport))
    if bad:
        with pytest.raises(RuntimeError, match='Planner unavailable'):
            asyncio.run(planner.plan('synthetic', None, {}, 1))
    else:
        assert json.loads(asyncio.run(planner.plan('synthetic', None, {}, 1)))['calls'] == []


def test_tool_audit_failure_rolls_back_review(db_client, db_sessions, synthetic_request):
    uuid = setup_request(db_client, synthetic_request)
    use_plan(db_client, [('create_human_review', {'request_uuid': uuid, 'reason': 'USER_REQUESTED'})])
    def reject_execution_audit(session, context, instances):
        if any(isinstance(row, AuditEvent) and row.event_type == 'AGENT_TOOL_EXECUTED' for row in session.new):
            raise RuntimeError('Synthetic audit failure')
    event.listen(db_sessions.class_, 'before_flush', reject_execution_audit)
    try:
        body = run(db_client, uuid).json()
        assert body['status'] == 'fallback' and not body['escalated']
        assert body['tools_used'] == []
    finally:
        event.remove(db_sessions.class_, 'before_flush', reject_execution_audit)
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 0
    assert db_client.get(f'/api/v1/requests/{uuid}').json()['system_decision'] is None


def test_database_lock_timeout_never_creates_late_review(db_client, db_sessions, synthetic_request):
    from uuid import UUID
    uuid = setup_request(db_client, synthetic_request)
    use_plan(db_client, [('create_human_review', {'request_uuid': uuid, 'reason': 'USER_REQUESTED'})])
    db_client.app.dependency_overrides[get_agent_settings] = lambda: AgentSettings(timeout_seconds=0.1)
    with db_sessions() as locker, locker.begin():
        locker.scalar(select(Request).where(Request.request_uuid == UUID(uuid)).with_for_update())
        body = run(db_client, uuid).json()
        assert body['status'] == 'fallback' and not body['escalated']
    with db_sessions() as session:
        assert session.scalar(select(func.count()).select_from(HumanReview)) == 0
