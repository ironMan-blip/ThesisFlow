
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.meeting import MeetingIn, MeetingListOut, MeetingOut, TaskDoneIn
from app.services import meeting_service

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
student = require_roles(Role.student)
faculty = require_roles(Role.faculty)


@router.get("/mine", response_model=MeetingListOut)
def mine(user: User = Depends(student), db: Session = Depends(get_db)):
    return meeting_service.mine(db, user)


@router.get("/thesis/{thesis_id}", response_model=MeetingListOut)
def for_thesis(thesis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return meeting_service.for_thesis(db, user, thesis_id)


@router.post("/thesis/{thesis_id}", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def record(thesis_id: int, data: MeetingIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return meeting_service.record(db, user, thesis_id, data)


@router.put("/tasks/{task_id}", response_model=MeetingOut)
def set_task_done(task_id: int, data: TaskDoneIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return meeting_service.set_task_done(db, user, task_id, data.done)


@router.put("/{meeting_id}", response_model=MeetingOut)
def update(meeting_id: int, data: MeetingIn, user: User = Depends(faculty), db: Session = Depends(get_db)):
    return meeting_service.update(db, user, meeting_id, data)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(meeting_id: int, user: User = Depends(faculty), db: Session = Depends(get_db)):
    meeting_service.delete(db, user, meeting_id)
