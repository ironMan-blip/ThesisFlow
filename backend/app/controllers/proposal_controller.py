from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.user import Role, User
from app.schemas.proposal import ProposalOut
from app.services import proposal_service

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("/mine", response_model=ProposalOut | None)
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


@router.get("/{proposal_id}", response_model=ProposalOut)
def get(proposal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return proposal_service.get_proposal(db, user, proposal_id)


@router.get("/versions/{version_id}/file")
def download(version_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    path, filename = proposal_service.get_version_file(db, user, version_id)
    return FileResponse(path, media_type="application/pdf", filename=filename)
