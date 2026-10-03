from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.healthcare_operations import HealthcareOperationsAgent
from app.agents.provider import AgentPlanner, get_agent_planner
from app.core.agent_config import AgentSettings, get_agent_settings
from app.db.session import get_session
from app.schemas.agent import AgentResponse, AgentRun

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/run", response_model=AgentResponse)
def run_agent(payload: AgentRun, session: Annotated[Session, Depends(get_session)],
              planner: Annotated[AgentPlanner, Depends(get_agent_planner)],
              settings: Annotated[AgentSettings, Depends(get_agent_settings)]) -> AgentResponse:
    return HealthcareOperationsAgent(planner, settings).run(payload, session)
