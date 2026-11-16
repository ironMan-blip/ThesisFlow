from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.proposal import ProposalOut
from app.schemas.thesis import DeleteRequestOut
from app.schemas.user import DeletionReasonIn
from app.services import proposal_service

router = APIRouter(prefix="/api/proposals", tags=["proposals"])
coordinator = require_roles(Role.coordinator)


@router.get("/mine", response_model=ProposalOut)
def mine(user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)):
    return proposal_service.get_mine(db, user)


@router.post("/mine/versions", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def upload(
    title: str = Form(...),
    abstract: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_roles(Role.student)),
    db: Session = Depends(get_db),
):
    return proposal_service.upload_version(db, user, title, abstract, file)


@router.get("/versions/{version_id}/file")
def download(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    path, filename = proposal_service.get_version_file(db, user, version_id)
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.post("/versions/{version_id}/delete-request", response_model=ProposalOut)
def request_delete(
    version_id: int, data: DeletionReasonIn, user: User = Depends(require_roles(Role.student)), db: Session = Depends(get_db)
):
    # Versions are kept (SRS F11): a delete needs a reason and the coordinator's approval, then waits 7 days, and
    # only the coordinator can cancel it.
    return proposal_service.request_delete(db, user, version_id, data.reason)


@router.post("/versions/{version_id}/deletion", status_code=status.HTTP_204_NO_CONTENT)
def schedule_delete(
    version_id: int, data: DeletionReasonIn, user: User = Depends(require_roles(Role.faculty)), db: Session = Depends(get_db),
):
    # The thesis's supervisor only: approved at once, runs in 7 days, never a final version.
    proposal_service.schedule_delete(db, user, version_id, data.reason)


@router.get("/delete-requests", response_model=list[DeleteRequestOut], dependencies=[Depends(coordinator)])
def delete_requests(db: Session = Depends(get_db)):
    return proposal_service.pending_delete_requests(db)


@router.post("/delete-requests/{version_id}/approve", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(coordinator)])
def approve_delete(version_id: int, db: Session = Depends(get_db)):
    proposal_service.approve_delete(db, version_id)


# Approved deletes run by themselves once their wait is over (proposal_service.run_due_deletions).
# DELETE rejects a request waiting for approval, or cancels an approved one.
@router.delete("/delete-requests/{version_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(coordinator)])
def cancel_delete(version_id: int, db: Session = Depends(get_db)):
    proposal_service.cancel_delete(db, version_id)
