"""Agent architecture: shared project state + decision log + the six cooperating agents.

PEAS  Performance: content preservation, duration accuracy, subtitle accuracy, visual continuity, audio quality, constraint satisfaction
      Environment: uploaded video/audio, metadata, user instructions, config
      Actuators  : trim, select, sequence, subtitle, audio-process, render
      Sensors    : frames, audio signal, transcript, scene-detection output, metadata
The agent is GOAL-based (works toward a target format/duration) and UTILITY-based (maximises scene importance minus
transition cost under constraints). Cycle: Perceive -> Understand -> Plan -> Decide -> Validate -> Act -> Evaluate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from ..models import AgentDecision
from ..utils.logger import get_logger

log = get_logger("agent")
PHASES = ["perceive", "understand", "plan", "decide", "validate", "act", "evaluate"]

AGENT_NAMES = {
    "perception": "Video Perception Agent", "speech": "Speech Analysis Agent", "scene": "Scene Evaluation Agent",
    "planner": "Editing Planner Agent", "constraint": "Constraint Validation Agent", "render": "Rendering Agent",
}


@dataclass
class AgentContext:
    """Shared project state read/written by every agent; every decision is persisted for explainability."""
    db: Session
    project_id: str
    state: dict = field(default_factory=dict)
    decisions: list = field(default_factory=list)

    def log(self, phase: str, agent: str, decision: str, explanation: str = "") -> None:
        assert phase in PHASES, phase
        name = AGENT_NAMES.get(agent, agent)
        log.info("[%s/%s] %s", name, phase, decision)
        self.db.add(AgentDecision(project_id=self.project_id, phase=phase, agent_name=name, decision=decision, explanation=explanation))
        self.db.commit()
        self.decisions.append((phase, name, decision))


def clear_decisions(db: Session, project_id: str, phases: set[str] | None = None, agents: set[str] | None = None) -> None:
    q = db.query(AgentDecision).filter(AgentDecision.project_id == project_id)
    if phases:
        q = q.filter(AgentDecision.phase.in_(phases))
    if agents:
        q = q.filter(AgentDecision.agent_name.in_({AGENT_NAMES.get(a, a) for a in agents}))
    q.delete(synchronize_session=False)
    db.commit()
