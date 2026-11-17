from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.semester import (
    BulkStepsUpdateIn,
    SemesterCreateIn,
    SemesterOut,
    StepKey,
    StepToggleIn,
)
from app.services import semester_service

router = APIRouter(prefix="/api/semesters", tags=["Semesters"])


@router.get("/current", response_model=SemesterOut)
def get_current_semester(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the active semester and the open/close status of every step."""
    semester = semester_service.get_active_semester(db)
    return semester_service.serialize_semester(semester, user)


@router.get("", response_model=list[SemesterOut])
def list_semesters(
    user: User = Depends(require_roles(Role.coordinator)),
    db: Session = Depends(get_db),
):
    """List all semesters, newest first."""
    return [semester_service.serialize_semester(s, user) for s in semester_service.list_semesters(db)]


@router.post("", response_model=SemesterOut, status_code=status.HTTP_201_CREATED)
def create_semester(
    data: SemesterCreateIn,
    user: User = Depends(require_roles(Role.coordinator)),
    db: Session = Depends(get_db),
):
    """Create a new semester (optionally rolling over active theses) and configure initial steps."""
    semester, summary = semester_service.create_semester(db, data)
    return semester_service.serialize_semester(semester, user, rollover_summary=summary)


@router.patch("/current/steps/{step}", response_model=SemesterOut)
def toggle_step(
    step: StepKey,
    data: StepToggleIn,
    user: User = Depends(require_roles(Role.coordinator)),
    db: Session = Depends(get_db),
):
    """Open or close a single step (form_group, pick_supervisor, P1, P2, P3, defense)."""
    semester = semester_service.set_step(db, step, data.is_open)
    return semester_service.serialize_semester(semester, user)


@router.patch("/current/steps", response_model=SemesterOut)
def update_steps(
    data: BulkStepsUpdateIn,
    user: User = Depends(require_roles(Role.coordinator)),
    db: Session = Depends(get_db),
):
    """Bulk update open/close states for steps in the current semester."""
    semester = semester_service.update_steps(db, data)
    return semester_service.serialize_semester(semester, user)