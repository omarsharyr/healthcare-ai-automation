import json
from uuid import uuid4

import pytest

from app.agents.tools import AgentScope, AgentToolRegistry, ToolDefinition, ToolRejected
from app.schemas.agent import EmptyInput, ToolCall
from app.services.ai_provider import FakeAIProvider
from app.services.request_classifier import RequestClassifier
from app.services.workflow_decision import WorkflowDecisionService


def test_browser_origin_cors_and_host_boundaries(client):
    for origin in ('https://evil.example', 'null', 'http://localhost.evil.example'):
        response = client.post('/api/v1/agent/run', json={'message':'synthetic'}, headers={'Origin':origin})
        assert response.status_code == 403
        assert 'access-control-allow-origin' not in response.headers
        assert 'X-Correlation-ID' in response.headers
    response = client.post('/api/v1/agent/run', json={'message':'hi'}, headers={'Origin':'http://localhost'})
    assert response.status_code == 422  # same-origin reaches schema validation
    assert client.get('/health', headers={'Host':'evil.example'}).status_code == 400
    assert client.get('/health', headers={'Origin':'https://evil.example'}).headers.get('access-control-allow-origin') is None
    assert client.get('/').status_code == 200  # redirects to Swagger


def test_body_limits_and_json_only_writes(client):
    for payload in ('x' * 70000, iter([b'x' * 40000, b'y' * 40000])):
        response = client.post('/api/v1/agent/run', content=payload, headers={'Content-Type':'application/json'})
        assert response.status_code == 413
        assert len(response.content) < 100
    assert client.post('/api/v1/requests', data={'request_text':'synthetic'}).status_code == 415
    assert client.post('/api/v1/agent/run', content='{bad', headers={'Content-Type':'application/json'}).status_code == 422


def test_future_high_impact_tools_fail_closed():
    registry = AgentToolRegistry()
    registry.tools = {'approve_review': ToolDefinition(EmptyInput, 'write')}
    with pytest.raises(ToolRejected, match='approval_required'):
        registry.validate(ToolCall(name='approve_review', arguments='{}'), AgentScope(None, True))


def test_prompt_injection_cannot_invent_tools_or_expand_scope():
    registry = AgentToolRegistry()
    scope = AgentScope(uuid4(), False)
    for name in ('delete_database', '__import__', 'approve_review', 'http_request', 'execute_code'):
        with pytest.raises(ToolRejected, match='unknown_tool'):
            registry.validate(ToolCall(name=name, arguments='{}'), scope)
    with pytest.raises(ToolRejected, match='outside_request_scope'):
        registry.validate(ToolCall(name='get_request_status', arguments=json.dumps({'request_uuid':str(uuid4())})), scope)


@pytest.mark.integration
def test_sql_payload_is_stored_as_data_and_errors_do_not_leak(db_client, synthetic_request):
    synthetic_request['request_text'] = "Synthetic input'); DROP TABLE requests; --"
    response = db_client.post('/api/v1/requests', json=synthetic_request)
    assert response.status_code == 201
    uuid = response.json()['request_uuid']
    assert db_client.get(f'/api/v1/requests/{uuid}').json()['request_text'] == synthetic_request['request_text']
    assert db_client.get('/api/v1/analytics/summary').json()['total_requests'] == 1
    rejected = db_client.get("/api/v1/requests/' OR 1=1 --")
    assert rejected.status_code == 422 and 'DROP TABLE' not in rejected.text


def test_offline_low_confidence_demo_exercises_override():
    result = RequestClassifier(FakeAIProvider()).classify('Synthetic claim status is uncertain.')
    assert result.output.category.value == 'CLAIM_STATUS'
    assert result.output.recommended_action.value == 'AUTO_PROCESS'
    assert result.output.confidence == .60
    decision = WorkflowDecisionService().decide(result)
    assert decision.decision.value == 'HUMAN_REVIEW' and decision.reason == 'Confidence below 0.85.'
