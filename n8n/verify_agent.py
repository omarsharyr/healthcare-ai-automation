"""Live fake-provider agent verification; leaves a synthetic pending review and audits."""
import subprocess

from verify_automation import ROOT, Settings, post
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models import AuditEvent, HumanReview


def main() -> None:
    subprocess.run(['docker', 'compose', 'exec', '-T', 'backend', 'python', '-c',
                    "from app.core.ai_config import get_ai_settings; assert get_ai_settings().ai_provider == 'fake'"],
                   cwd=ROOT, check=True, capture_output=True)
    settings = Settings()
    api = f'http://127.0.0.1:{settings.api_port}/api/v1'
    webhook = f'http://127.0.0.1:{settings.n8n_port}/webhook/healthcare-agent-operations'
    status, created = post(f'{api}/requests', {'patient_reference': 'PAT-60606',
        'request_text': 'Synthetic administrative claim status inquiry.', 'source': 'api', 'priority': 'normal'})
    assert status == 201
    uuid = created['request_uuid']
    for message, expected in [('Check status and history', False), ('Check status and escalate to human review', True)]:
        status, body = post(webhook, {'message': message, 'request_uuid': uuid})
        assert status == 200 and body['status'] == 'completed'
        assert body['escalated'] is expected
        with get_session_factory()() as session:
            events = session.scalars(select(AuditEvent).where(AuditEvent.event_metadata['run_uuid'].astext == body['run_uuid'])).all()
            types = [e.event_type for e in events]
            assert 'AGENT_STARTED' in types and 'AGENT_COMPLETED' in types
            assert types.count('AGENT_TOOL_EXECUTED') == len(body['tools_used'])
            if expected:
                review_id = next(r['output']['review_id'] for r in body['results'] if r['tool'] == 'create_human_review')
                assert session.get(HumanReview, review_id).status.value == 'PENDING'
                assert 'HUMAN_REVIEW_REQUESTED' in types
        print(f"PASS: webhook agent escalated={expected}; run={body['run_uuid']}")
    status, body = post(webhook, {'message': 'Check request REQ-123'})
    assert status == 200 and body['human_action_required'] and not body['escalated']
    assert post(webhook, {'message': 'hi'})[0] == 422
    print('PASS: missing UUID requires manual action; invalid input rejected; synthetic pending review retained.')


if __name__ == '__main__':
    main()
