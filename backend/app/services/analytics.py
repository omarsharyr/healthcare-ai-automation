"""Read-only aggregates. Never select healthcare text, references or reviewer notes."""
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.agents.tools import AgentToolRegistry
from app.core.enums import RequestCategory, RequestStatus, WorkflowDecision
from app.models import AuditEvent, HumanReview, Request
from app.schemas.analytics import ActivityItem, ActivityResponse, AnalyticsFilters, AnalyticsSummary


def date_conditions(column, filters: AnalyticsFilters) -> list:
    conditions = []
    if filters.date_from:
        conditions.append(column >= datetime.combine(filters.date_from, time.min, timezone.utc))
    if filters.date_to:
        conditions.append(column < datetime.combine(filters.date_to + timedelta(days=1), time.min, timezone.utc))
    return conditions


def request_conditions(filters: AnalyticsFilters) -> list:
    conditions = date_conditions(Request.created_at, filters)
    if filters.category:
        conditions.append(Request.category == filters.category)
    if filters.status:
        conditions.append(Request.status == filters.status)
    return conditions


def event_conditions(filters: AnalyticsFilters) -> list:
    conditions = date_conditions(AuditEvent.created_at, filters)
    if filters.category or filters.status:
        cohort = select(Request.id).where(*request_conditions(filters))
        # Global agent start/failure/completion events link through their run UUID.
        linked_runs = select(AuditEvent.event_metadata['run_uuid'].astext).where(AuditEvent.request_id.in_(cohort))
        conditions.append(or_(AuditEvent.request_id.in_(cohort), AuditEvent.event_metadata['run_uuid'].astext.in_(linked_runs)))
    return conditions


def summary(session: Session, filters: AnalyticsFilters) -> AnalyticsSummary:
    # All cards/charts in a response share a repeatable read snapshot.
    with session.begin():
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        conditions = request_conditions(filters)
        reviewed = exists(select(HumanReview.id).where(HumanReview.request_id == Request.id))
        automated = and_(Request.status == RequestStatus.PROCESSED,
                         Request.system_decision == WorkflowDecision.AUTO_PROCESS, ~reviewed)
        completed = and_(Request.status == RequestStatus.PROCESSED,
                         Request.system_decision.in_([WorkflowDecision.AUTO_PROCESS, WorkflowDecision.REJECT]))
        pending = or_(Request.status == RequestStatus.RECEIVED, Request.system_decision == WorkflowDecision.HUMAN_REVIEW)
        row = session.execute(select(
            func.count(), func.count().filter(completed), func.count().filter(pending),
            func.count().filter(automated), func.count().filter(Request.status == RequestStatus.FAILED),
            func.avg(Request.confidence),
        ).select_from(Request).where(*conditions)).one()
        total, complete, pending_count, automatic, failures, confidence = row
        review_counts = session.execute(select(func.count(), func.count().filter(HumanReview.status == 'PENDING'))
                                       .select_from(HumanReview).join(Request, Request.id == HumanReview.request_id)
                                       .where(*conditions)).one()
        def grouped(column, labels: list[str], empty_label: str | None = None) -> dict[str, int]:
            values = {label: 0 for label in labels}
            if empty_label:
                values[empty_label] = 0
            for key, count in session.execute(select(column, func.count()).where(*conditions).group_by(column)):
                values[key.value if key is not None else empty_label] = count
            return values
        categories = grouped(Request.category, [c.value for c in RequestCategory], 'UNCLASSIFIED')
        decisions = grouped(Request.system_decision, [d.value for d in WorkflowDecision], 'UNDECIDED')
        statuses = grouped(Request.status, [s.value for s in RequestStatus])
        event_filter = event_conditions(filters)
        event_counts = dict(session.execute(select(AuditEvent.event_type, func.count()).where(*event_filter)
                                            .group_by(AuditEvent.event_type)).all())
        run = AuditEvent.event_metadata['run_uuid'].astext
        agent_failures = session.scalar(select(func.count(func.distinct(run))).where(*event_filter, AuditEvent.event_type == 'AGENT_FAILED'))
        usage = {name: 0 for name in AgentToolRegistry.tools}
        tool_expression = AuditEvent.event_metadata['tool'].astext
        for tool, count in session.execute(select(tool_expression, func.count())
                                           .where(*event_filter, AuditEvent.event_type == 'AGENT_TOOL_EXECUTED')
                                           .group_by(tool_expression)):
            if tool in usage:
                usage[tool] = count
        return AnalyticsSummary(
            total_requests=total, completed_requests=complete, pending_requests=pending_count, automated=automatic,
            human_reviews=review_counts[0], pending_reviews=review_counts[1], failures=failures,
            automation_rate=round(100 * automatic / total, 2) if total else 0,
            average_ai_confidence=float(confidence) if confidence is not None else None,
            requests_by_category=categories, requests_by_decision=decisions, requests_by_status=statuses,
            agent_executions=event_counts.get('AGENT_STARTED', 0), agent_failures=agent_failures,
            agent_tool_calls=event_counts.get('AGENT_TOOL_EXECUTED', 0),
            agent_tool_rejections=event_counts.get('AGENT_TOOL_REJECTED', 0), agent_tool_usage=usage,
            ai_failures=event_counts.get('AI_CLASSIFICATION_FAILED', 0),
        )


def activity(session: Session, filters: AnalyticsFilters, limit: int) -> ActivityResponse:
    known_events = {'REQUEST_RECEIVED', 'PHI_REDACTION_COMPLETED', 'AI_CLASSIFICATION_STARTED',
                    'AI_CLASSIFICATION_COMPLETED', 'AI_CLASSIFICATION_FAILED', 'WORKFLOW_DECISION_MADE',
                    'HUMAN_REVIEW_REQUESTED', 'HUMAN_REVIEW_COMPLETED', 'WORKFLOW_COMPLETED', 'WORKFLOW_FAILED',
                    'AGENT_STARTED', 'AGENT_TOOL_REQUESTED', 'AGENT_TOOL_EXECUTED', 'AGENT_TOOL_REJECTED',
                    'AGENT_COMPLETED', 'AGENT_FAILED'}
    rows = session.execute(select(AuditEvent.id, AuditEvent.created_at, AuditEvent.event_type, AuditEvent.actor,
                                  AuditEvent.correlation_id, AuditEvent.event_metadata['run_uuid'].astext)
                           .where(*event_conditions(filters)).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit))
    items = []
    for event_id, created_at, event_type, actor, trace, run in rows:
        try:
            run_uuid = UUID(run) if run else None
        except ValueError:
            run_uuid = None
        items.append(ActivityItem(event_id=event_id, created_at=created_at,
                                  event_type=event_type if event_type in known_events else 'OTHER_EVENT',
                                  actor=actor if actor in {'api', 'system', 'agent', 'human_reviewer'} else 'other',
                                  correlation_id=trace, run_uuid=run_uuid))
    return ActivityResponse(items=items)
