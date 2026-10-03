"""Trusted application tools. No user/model text is evaluated as SQL, code or a URL."""
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, ReviewStatus, WorkflowDecision
from app.models import AuditEvent, HumanReview, Request
from app.schemas.agent import (CountOutput, DocumentsInput, DocumentsOutput, EmptyInput, EscalationInput,
                               HistoryOutput, RequestToolInput, ReviewOutput, StatusOutput, ToolCall, ToolResult)


class ToolRejected(Exception):
    """Only controlled reason codes may be supplied."""


@dataclass(frozen=True)
class AgentScope:
    request_uuid: UUID | None
    allow_global_count: bool


@dataclass(frozen=True)
class ToolDefinition:
    input_schema: type[BaseModel]
    effect: str


class AgentToolRegistry:
    # There is deliberately no dynamic registration, import, getattr or code evaluation.
    tools = MappingProxyType({
        "get_request_status": ToolDefinition(RequestToolInput, "read"),
        "get_request_history": ToolDefinition(RequestToolInput, "read"),
        "get_required_documents": ToolDefinition(DocumentsInput, "read"),
        "create_human_review": ToolDefinition(EscalationInput, "escalation"),
        "get_pending_review_count": ToolDefinition(EmptyInput, "read"),
    })

    def schemas(self) -> dict:
        return {name: definition.input_schema.model_json_schema() for name, definition in self.tools.items()}

    def validate(self, call: ToolCall, scope: AgentScope) -> BaseModel:
        definition = self.tools.get(call.name)
        if definition is None:
            raise ToolRejected("unknown_tool")
        # Future writes default to denial until a separate explicit approval flow exists.
        if definition.effect not in ("read", "escalation") or (
            definition.effect == "escalation" and call.name != "create_human_review"
        ):
            raise ToolRejected("approval_required")
        try:
            arguments = definition.input_schema.model_validate_json(call.arguments)
        except ValueError:
            raise ToolRejected("malformed_arguments") from None
        if isinstance(arguments, RequestToolInput) and (
            scope.request_uuid is None or arguments.request_uuid != scope.request_uuid
        ):
            raise ToolRejected("outside_request_scope")
        if call.name == "get_pending_review_count" and not scope.allow_global_count:
            raise ToolRejected("global_count_denied")
        return arguments

    def execute(self, call: ToolCall, scope: AgentScope, session: Session, run_uuid: UUID,
                deadline: float) -> ToolResult:
        arguments = self.validate(call, scope)
        with session.begin():
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ToolRejected("deadline_exceeded")
            # Parameterized, transaction-local query/lock limits; never interpolate model input.
            session.execute(text("SELECT set_config('statement_timeout', :timeout, true)"),
                            {"timeout": str(max(1, min(3000, int(remaining * 1000))))})
            request = None
            if isinstance(arguments, RequestToolInput):
                query = select(Request).where(Request.request_uuid == arguments.request_uuid)
                if call.name == "create_human_review":
                    query = query.with_for_update()
                request = session.scalar(query)
                if request is None:
                    raise ToolRejected("request_not_found")
            if call.name == "get_request_status":
                output = StatusOutput(request_uuid=request.request_uuid, status=request.status,
                                      category=request.category, system_decision=request.system_decision)
            elif call.name == "get_request_history":
                events = list(session.scalars(select(AuditEvent.event_type).where(AuditEvent.request_id == request.id)
                                             .order_by(AuditEvent.id.desc()).limit(51)))
                output = HistoryOutput(request_uuid=request.request_uuid, event_types=events[:50], truncated=len(events) > 50)
            elif call.name == "get_required_documents":
                # Illustrative portfolio checklist, not an insurer's policy or medical advice.
                documents = {
                    "CLAIM_STATUS": ["Synthetic claim submission receipt"],
                    "MISSING_INFORMATION": ["Synthetic information request notice", "Synthetic supporting form"],
                    "BILLING_QUESTION": ["Synthetic invoice"],
                    "DOCUMENT_PROCESSING": ["Readable synthetic source document"],
                    "OTHER": ["Human review required to identify documents"],
                }
                output = DocumentsOutput(category=arguments.category, documents=documents[arguments.category.value])
            elif call.name == "get_pending_review_count":
                output = CountOutput(pending_count=session.scalar(select(func.count()).select_from(HumanReview)
                                                                  .where(HumanReview.status == ReviewStatus.PENDING)))
            elif call.name == "create_human_review":
                review = session.scalar(select(HumanReview).where(HumanReview.request_id == request.id))
                if review is not None and review.status != ReviewStatus.PENDING:
                    raise ToolRejected("review_already_resolved")
                created = review is None
                if created:
                    review = HumanReview(request_id=request.id, ai_recommendation=request.ai_recommendation)
                    session.add(review)
                    request.system_decision = WorkflowDecision.HUMAN_REVIEW
                    request.status = RequestStatus.PROCESSED
                    request.decision_reason = "Operations agent requested human review."
                    session.add(AuditEvent(request_id=request.id, event_type="HUMAN_REVIEW_REQUESTED", actor="agent",
                                           event_metadata={"run_uuid": str(run_uuid), "reason_code": arguments.reason}))
                    session.flush()
                output = ReviewOutput(review_id=review.id, status=review.status, created=created)
            else:
                raise ToolRejected("unknown_tool")
            if monotonic() >= deadline:
                raise ToolRejected("deadline_exceeded")
            session.add(AuditEvent(request_id=request.id if request else None, event_type="AGENT_TOOL_EXECUTED", actor="agent",
                                   event_metadata={"run_uuid": str(run_uuid), "tool": call.name}))
            result = ToolResult(tool=call.name, output=output)
        return result
