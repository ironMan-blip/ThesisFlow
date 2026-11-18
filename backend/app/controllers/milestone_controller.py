from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.milestone import Phase
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, RegistrationIn, TimelineOut
from app.services import milestone_service, progress_service

router = APIRouter(prefix="/api/milestones", tags=["milestones"])


@router.get("", response_model=TimelineOut)
def timeline(semester_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # semester_id: the coordinator picks whose deadlines to see; everyone else gets the current semester's.
    return milestone_service.timeline(db, user, semester_id)


# Declared before /{phase}, which would otherwise read "registration" as a phase.
@router.put("/registration", response_model=TimelineOut)
def set_registration(
    data: RegistrationIn, user: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)
):
    milestone_service.set_registration(db, data)
    return milestone_service.timeline(db, user, data.semester_id)


@router.put("/{phase}", response_model=TimelineOut)
def set_deadline(
    phase: Phase, data: MilestoneIn, user: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)
):
    milestone_service.set_milestone(db, phase, data)
    return milestone_service.timeline(db, user, data.semester_id)


@router.post("/next-semester", dependencies=[Depends(require_roles(Role.coordinator))])
def next_semester(db: Session = Depends(get_db)) -> dict[str, int]:
    return progress_service.next_semester(db)
