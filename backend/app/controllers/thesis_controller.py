from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.user import Role, User
from app.schemas.thesis import (
    CoSupervisorIn,
    DeferIn,
    MyThesisOut,
    SupervisionRequestOut,
    ThesisDetailOut,
    ThesisOut,
    ThesisRequestIn,
)
from app.services import progress_service, thesis_service

router = APIRouter(prefix="/api/theses", tags=["theses"])
student = require_roles(Role.student)
faculty = require_roles(Role.faculty)


@router.get("/mine", response_model=MyThesisOut)
def mine(user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.mine(db, user)


@router.post("/mine", response_model=MyThesisOut, status_code=status.HTTP_201_CREATED)
def request_group(data: ThesisRequestIn, user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.request_group(db, user, data)


@router.post("/mine/register", response_model=MyThesisOut)
def register_p1(user: User = Depends(student), db: Session = Depends(get_db)):
    progress_service.register_p1(db, user)
    return thesis_service.mine(db, user)


@router.delete("/mine", response_model=MyThesisOut)
def cancel(user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.cancel(db, user)


@router.post("/mine/co-supervisor", response_model=MyThesisOut)
def add_co_supervisor(data: CoSupervisorIn, user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.add_co_supervisor(db, user, data.co_supervisor_id)


@router.delete("/mine/co-supervisor", response_model=MyThesisOut)
def cancel_co_supervisor(user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.cancel_co_supervisor(db, user)


@router.get("/requests", response_model=list[SupervisionRequestOut])
def requests(user: User = Depends(faculty), db: Session = Depends(get_db)):
    return thesis_service.requests_for(db, user)


@router.post("/requests/{thesis_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept(thesis_id: int, co_supervisor_id: int | None = None, user: User = Depends(faculty), db: Session = Depends(get_db)):
    thesis_service.decide(db, user, thesis_id, accept=True, co_supervisor_id=co_supervisor_id)


@router.post("/requests/{thesis_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline(thesis_id: int, co_supervisor_id: int | None = None, user: User = Depends(faculty), db: Session = Depends(get_db)):
    thesis_service.decide(db, user, thesis_id, accept=False, co_supervisor_id=co_supervisor_id)


# Faculty only: the coordinator runs semesters and accounts, not individual theses.
@router.get("", response_model=list[ThesisDetailOut])
def theses(user: User = Depends(faculty), db: Session = Depends(get_db)):
    return thesis_service.list_theses(db, user)


@router.put("/{thesis_id}/defer", response_model=ThesisOut)
def defer(thesis_id: int, data: DeferIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return progress_service.set_defer(db, user, thesis_id, data.defer)
