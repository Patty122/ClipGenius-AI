from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database.connection import Base


def now():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    project_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(200))
    original_video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)   # relative to uploads dir; never exposed
    original_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    music_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="created")
    stage: Mapped[str] = mapped_column(String(80), default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    scenes = relationship("Scene", cascade="all, delete-orphan", order_by="Scene.scene_id")
    plans = relationship("EditingPlan", cascade="all, delete-orphan", order_by="EditingPlan.created_at")
    jobs = relationship("RenderJob", cascade="all, delete-orphan", order_by="RenderJob.created_at")
    decisions = relationship("AgentDecision", cascade="all, delete-orphan", order_by="AgentDecision.decision_id")


class Scene(Base):
    __tablename__ = "scenes"
    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    transcript: Mapped[str] = mapped_column(Text, default="")
    thumbnail_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # full feature dict


class EditingPlan(Base):
    __tablename__ = "editing_plans"
    plan_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), index=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    selected_scenes: Mapped[list] = mapped_column(JSON)
    editing_operations: Mapped[list] = mapped_column(JSON)
    validation_status: Mapped[str] = mapped_column(String(16), default="unvalidated")
    data: Mapped[dict] = mapped_column(JSON)       # full plan incl. A*/CSP/expert-system results
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RenderJob(Base):
    __tablename__ = "render_jobs"
    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="final")   # final | preview
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(80), default="")
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    decision_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), index=True)
    phase: Mapped[str] = mapped_column(String(16), default="")   # perceive|understand|plan|decide|validate|act|evaluate
    agent_name: Mapped[str] = mapped_column(String(60))
    decision: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
