from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.user import Role, User
from app.schemas.group import GroupCreate, InviteIn, MyGroupOut, ProfileIn, ProfileOut, TeammateOut
from app.services import group_service

router = APIRouter(prefix="/api/groups", tags=["groups"])
student = require_roles(Role.student)


@router.get("/mine", response_model=MyGroupOut)
def mine(user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.mine(db, user)


@router.post("/mine", response_model=MyGroupOut, status_code=status.HTTP_201_CREATED)
def create(data: GroupCreate, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.create(db, user, data)


@router.delete("/mine", response_model=MyGroupOut)
def leave(user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.leave(db, user)


@router.post("/mine/invitations", response_model=MyGroupOut, status_code=status.HTTP_201_CREATED)
def invite(data: InviteIn, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.invite(db, user, data.student_id)


@router.delete("/mine/invitations/{invitation_id}", response_model=MyGroupOut)
def cancel_invitation(invitation_id: int, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.cancel_invitation(db, user, invitation_id)


@router.post("/invitations/{invitation_id}/accept", response_model=MyGroupOut)
def accept(invitation_id: int, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.decide(db, user, invitation_id, accept=True)


@router.post("/invitations/{invitation_id}/decline", response_model=MyGroupOut)
def decline(invitation_id: int, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.decide(db, user, invitation_id, accept=False)


@router.get("/teammates", response_model=list[TeammateOut])
def teammates(q: str = "", user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.teammates(db, user, q)


@router.get("/profile", response_model=ProfileOut)
def profile(user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.get_profile(db, user)


@router.put("/profile", response_model=ProfileOut)
def save_profile(data: ProfileIn, user: User = Depends(student), db: Session = Depends(get_db)):
    return group_service.save_profile(db, user, data)
