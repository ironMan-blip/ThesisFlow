from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.user import Role, User
from app.schemas.thesis import (
    DeferIn,
    MyThesisOut,
    PersonOut,
    SupervisionRequestOut,
    ThesisDetailOut,
    ThesisOut,
    ThesisRequestIn,
)
from app.services import progress_service, thesis_service

router = APIRouter(prefix="/api/theses", tags=["theses"])
student = require_roles(Role.student)
faculty = require_roles(Role.faculty)
staff = require_roles(Role.faculty, Role.coordinator)


@router.get("/faculty", response_model=list[PersonOut], dependencies=[Depends(student)])
def faculty_list(db: Session = Depends(get_db)):
    return thesis_service.faculty(db)


@router.get("/mine", response_model=MyThesisOut)
def mine(user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.mine(db, user)


@router.post("/mine", response_model=MyThesisOut, status_code=status.HTTP_201_CREATED)
def request_group(data: ThesisRequestIn, user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.request_group(db, user, data)


@router.delete("/mine", response_model=MyThesisOut)
def cancel(user: User = Depends(student), db: Session = Depends(get_db)):
    return thesis_service.cancel(db, user)


@router.get("/requests", response_model=list[SupervisionRequestOut])
def requests(user: User = Depends(faculty), db: Session = Depends(get_db)):
    return thesis_service.requests_for(db, user)


@router.post("/requests/{thesis_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept(thesis_id: int, user: User = Depends(faculty), db: Session = Depends(get_db)):
    thesis_service.decide(db, user, thesis_id, accept=True)


@router.post("/requests/{thesis_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline(thesis_id: int, user: User = Depends(faculty), db: Session = Depends(get_db)):
    thesis_service.decide(db, user, thesis_id, accept=False)


@router.get("", response_model=list[ThesisDetailOut])
def theses(user: User = Depends(staff), db: Session = Depends(get_db)):
    return thesis_service.list_theses(db, user)


@router.put("/{thesis_id}/defer", response_model=ThesisOut, dependencies=[Depends(require_roles(Role.coordinator))])
def defer(thesis_id: int, data: DeferIn, db: Session = Depends(get_db)):
    return progress_service.set_defer(db, thesis_id, data.defer)
