from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..models import Project


def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p
