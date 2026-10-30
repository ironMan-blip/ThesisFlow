from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.milestone import Phase
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, TimelineOut
from app.services import milestone_service

router = APIRouter(prefix="/api/milestones", tags=["milestones"])


@router.get("", response_model=TimelineOut)
def timeline(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return milestone_service.timeline(db, user)


@router.put("/{phase}", response_model=TimelineOut)
def set_deadline(
    phase: Phase, data: MilestoneIn, user: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)
):
    milestone_service.set_milestone(db, phase, data)
    return milestone_service.timeline(db, user)
