from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.user import DeletionRequestOut, FacultyRequestOut, UserOut
from app.services import account_service

# Same /api/auth prefix as auth_controller, so existing URLs keep working.
router = APIRouter(prefix="/api/auth", tags=["accounts"])
coordinator = require_roles(Role.coordinator)


@router.post("/me/deletion-request", response_model=UserOut)
def request_deletion(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return account_service.request_deletion(db, user)


@router.get("/faculty-requests", response_model=list[FacultyRequestOut], dependencies=[Depends(coordinator)])
def faculty_requests(db: Session = Depends(get_db)):
    return account_service.pending_faculty(db)


@router.post("/faculty-requests/{user_id}/approve", response_model=UserOut, dependencies=[Depends(coordinator)])
def approve(user_id: int, db: Session = Depends(get_db)):
    return account_service.approve_faculty(db, user_id)


@router.delete(
    "/faculty-requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(coordinator)]
)
def reject(user_id: int, db: Session = Depends(get_db)):
    account_service.reject_faculty(db, user_id)


@router.get("/deletion-requests", response_model=list[DeletionRequestOut], dependencies=[Depends(coordinator)])
def deletion_requests(db: Session = Depends(get_db)):
    return account_service.pending_deletions(db)


@router.post(
    "/deletion-requests/{user_id}/approve", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(coordinator)]
)
def approve_deletion(user_id: int, db: Session = Depends(get_db)):
    account_service.approve_deletion(db, user_id)


@router.delete("/deletion-requests/{user_id}", response_model=UserOut, dependencies=[Depends(coordinator)])
def reject_deletion(user_id: int, db: Session = Depends(get_db)):
    return account_service.reject_deletion(db, user_id)
