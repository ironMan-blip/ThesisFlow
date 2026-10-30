from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.user import FacultyRequestOut, Token, UserCreate, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register(db, data)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses "username"; we treat it as the email.
    return Token(access_token=auth_service.login(db, form.username, form.password))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/faculty-requests", response_model=list[FacultyRequestOut])
def faculty_requests(_: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)):
    return auth_service.pending_faculty(db)


@router.post("/faculty-requests/{user_id}/approve", response_model=UserOut)
def approve(user_id: int, _: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)):
    return auth_service.approve_faculty(db, user_id)


@router.delete("/faculty-requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def reject(user_id: int, _: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)):
    auth_service.reject_faculty(db, user_id)
