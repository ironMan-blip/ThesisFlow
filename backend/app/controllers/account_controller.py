from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.user import DeletionReasonIn, DeletionRequestOut, RegistrationRequestOut, RestartRequestOut, UserOut
from app.services import account_service, progress_service

# Same /api/auth prefix as auth_controller, so existing URLs keep working.
router = APIRouter(prefix="/api/auth", tags=["accounts"])
coordinator = require_roles(Role.coordinator)


@router.post("/me/deletion-request", response_model=UserOut)
def request_deletion(data: DeletionReasonIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return account_service.request_deletion(db, user, data.reason)


@router.get("/registration-requests", response_model=list[RegistrationRequestOut], dependencies=[Depends(coordinator)])
def registration_requests(db: Session = Depends(get_db)):
    return account_service.pending_registrations(db)


@router.post("/registration-requests/{user_id}/approve", response_model=UserOut, dependencies=[Depends(coordinator)])
def approve(user_id: int, db: Session = Depends(get_db)):
    return account_service.approve_registration(db, user_id)


@router.delete(
    "/registration-requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(coordinator)]
)
def reject(user_id: int, db: Session = Depends(get_db)):
    account_service.reject_registration(db, user_id)


@router.get("/deletion-requests", response_model=list[DeletionRequestOut], dependencies=[Depends(coordinator)])
def deletion_requests(db: Session = Depends(get_db)):
    return account_service.pending_deletions(db)


@router.post("/deletion-requests/{user_id}/approve", response_model=UserOut, dependencies=[Depends(coordinator)])
def approve_deletion(user_id: int, db: Session = Depends(get_db)):
    return account_service.approve_deletion(db, user_id)


# Approved deletions run by themselves once their wait is over (account_service.run_due_deletions).
# DELETE rejects a request waiting for approval, or cancels an approved one.
@router.delete("/deletion-requests/{user_id}", response_model=UserOut, dependencies=[Depends(coordinator)])
def cancel_deletion(user_id: int, db: Session = Depends(get_db)):
    return account_service.cancel_deletion(db, user_id)


@router.post("/me/restart-request", response_model=UserOut)
def request_restart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return progress_service.request_restart(db, user)


@router.get("/restart-requests", response_model=list[RestartRequestOut], dependencies=[Depends(coordinator)])
def restart_requests(db: Session = Depends(get_db)):
    return progress_service.pending_restarts(db)


@router.post("/restart-requests/{user_id}/approve", response_model=UserOut, dependencies=[Depends(coordinator)])
def approve_restart(user_id: int, db: Session = Depends(get_db)):
    return progress_service.approve_restart(db, user_id)


@router.delete("/restart-requests/{user_id}", response_model=UserOut, dependencies=[Depends(coordinator)])
def reject_restart(user_id: int, db: Session = Depends(get_db)):
    return progress_service.reject_restart(db, user_id)


@router.get("/me/counts")
def counts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    return account_service.pending_counts(db, user)


@router.get("/accounts", response_model=list[UserOut], dependencies=[Depends(coordinator)])
def accounts(role: Literal[Role.student, Role.faculty] | None = None, id_prefix: str = "", db: Session = Depends(get_db)):
    return account_service.list_accounts(db, role, id_prefix.strip())


@router.post("/accounts/{user_id}/deletion", response_model=UserOut)
def schedule_deletion(
    user_id: int, data: DeletionReasonIn, user: User = Depends(coordinator), db: Session = Depends(get_db)
):
    return account_service.schedule_deletion(db, user, user_id, data.reason)
