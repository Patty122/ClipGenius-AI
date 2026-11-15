from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database.connection import get_db
from ...models import AgentDecision, Project
from ...services.planning_service import latest_plan
from ..deps import get_project

router = APIRouter(prefix="/api", tags=["agents", "algorithms"])


def _plan(db, p):
    row = latest_plan(db, p.project_id)
    if not row:
        raise HTTPException(404, "No plan yet")
    return row.data


@router.get("/agents/{project_id}/decisions")
def decisions(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    rows = db.query(AgentDecision).filter(AgentDecision.project_id == p.project_id).order_by(AgentDecision.decision_id).all()
    return [{"decision_id": r.decision_id, "phase": r.phase, "agent_name": r.agent_name, "decision": r.decision, "explanation": r.explanation,
             "timestamp": r.timestamp.isoformat()} for r in rows]


@router.get("/algorithms/{project_id}/astar")
def astar(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    return _plan(db, p)["algorithms"]["astar"]


@router.get("/algorithms/{project_id}/csp")
def csp(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    d = _plan(db, p)
    return {**d["algorithms"]["csp"], "validation": d["validation"]}


@router.get("/algorithms/{project_id}/expert-system")
def expert(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    return _plan(db, p)["algorithms"]["expert"]
