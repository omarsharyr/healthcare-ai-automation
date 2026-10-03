import asyncio
import json
import re
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agents.provider import AgentPlanner
from app.agents.tools import AgentScope, AgentToolRegistry, ToolRejected
from app.core.agent_config import AgentSettings
from app.models import AuditEvent
from app.schemas.agent import AgentPlan, AgentResponse, AgentRun, ReviewOutput, ToolCall, ToolResult
from app.services.phi_redaction import PHIRedactionService


class HealthcareOperationsAgent:
    def __init__(self, planner: AgentPlanner, settings: AgentSettings) -> None:
        self.planner, self.settings = planner, settings
        self.registry = AgentToolRegistry()

    def run(self, payload: AgentRun, session: Session) -> AgentResponse:
        run_uuid = uuid4()
        deadline = monotonic() + self.settings.timeout_seconds
        # Scope comes from validated caller input, never from the model's invented arguments.
        identifiers = set(re.findall(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", payload.message))
        request_uuid = payload.request_uuid or (UUID(next(iter(identifiers))) if len(identifiers) == 1 else None)
        scope = AgentScope(request_uuid, self.settings.allow_global_count)
        results: list[ToolResult] = []
        attempts = 0

        def audit(event: str, **metadata: str) -> None:
            # Global audits correlate by run_uuid; no raw message, arguments or model reasoning.
            with session.begin():
                session.add(AuditEvent(request_id=None, event_type=event, actor="agent",
                                       event_metadata={"run_uuid": str(run_uuid), **metadata}))

        def execute(call: ToolCall) -> None:
            nonlocal attempts
            if attempts >= self.settings.max_tool_calls:
                raise ToolRejected("tool_limit")
            attempts += 1
            safe_name = call.name if call.name in self.registry.tools else "unregistered"
            audit("AGENT_TOOL_REQUESTED", tool=safe_name)
            try:
                result = self.registry.execute(call, scope, session, run_uuid, deadline)
            except ToolRejected as error:
                audit("AGENT_TOOL_REJECTED", tool=safe_name, reason_code=str(error))
                raise
            results.append(result)

        audit("AGENT_STARTED")
        failure = None
        try:
            redacted = PHIRedactionService().redact(payload.message).text
            async def plan() -> str:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                return await asyncio.wait_for(self.planner.plan(redacted, request_uuid, self.registry.schemas(), remaining), remaining)
            raw = asyncio.run(plan())
            if not isinstance(raw, str) or len(raw) > 20000:
                raise ValueError()
            planned = AgentPlan.model_validate_json(raw)
            if len(planned.calls) > self.settings.max_tool_calls:
                audit("AGENT_TOOL_REJECTED", tool="plan", reason_code="tool_limit")
                raise ToolRejected("tool_limit")
            # Preflight the entire plan: a malicious later call cannot follow an earlier write.
            for call in planned.calls:
                try:
                    self.registry.validate(call, scope)
                except ToolRejected as error:
                    audit("AGENT_TOOL_REQUESTED", tool=call.name if call.name in self.registry.tools else "unregistered")
                    audit("AGENT_TOOL_REJECTED", reason_code=str(error))
                    raise
            if planned.intent == "unsupported" or not planned.calls:
                raise ToolRejected("unsupported_intent")
            for call in planned.calls:
                execute(call)
        except TimeoutError:
            failure = "deadline_exceeded"
        except ToolRejected as error:
            failure = str(error)
        except Exception:
            failure = "planner_or_tool_failure"
        if failure:
            audit("AGENT_FAILED", reason_code=failure)
            # Safe fallback stays within the SAME budget, deadline, registry and scope.
            if request_uuid and attempts < self.settings.max_tool_calls and monotonic() < deadline:
                try:
                    execute(ToolCall(name="create_human_review", arguments=json.dumps({
                        "request_uuid": str(request_uuid), "reason": "AGENT_FAILURE"})))
                except Exception:
                    # No raw exception is exposed; failure to escalate is not reported as success.
                    audit("AGENT_FAILED", reason_code="escalation_unavailable")
        escalated = any(isinstance(result.output, ReviewOutput) for result in results)
        response = AgentResponse(
            run_uuid=run_uuid, tools_used=[r.tool for r in results], results=results,
            escalated=escalated, human_action_required=escalated or failure is not None,
            status="fallback" if failure else "completed",
            response=("Human review is pending." if escalated else
                      "Unable to complete safely; manual investigation is required." if failure else
                      "Approved operations completed. See structured results."),
        )
        audit("AGENT_COMPLETED", outcome=response.status, escalated=str(escalated).lower())
        return response
