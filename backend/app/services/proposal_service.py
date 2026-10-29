import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.proposal import Proposal, ProposalVersion
from app.models.user import Role, User

CHUNK = 1024 * 1024


def _upload_dir() -> Path:
    path = Path(settings.upload_dir) / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _can_view(user: User, proposal: Proposal) -> bool:
    # Faculty and coordinator see all proposals (review, F13); students only their own.
    return user.role in (Role.faculty, Role.coordinator) or proposal.owner_id == user.id


def get_mine(db: Session, user: User) -> Proposal | None:
    return db.scalar(select(Proposal).where(Proposal.owner_id == user.id))


def get_proposal(db: Session, user: User, proposal_id: int) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None or not _can_view(user, proposal):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found")
    return proposal


def _save_pdf(file: UploadFile) -> tuple[str, int]:
    """Stream the upload to disk. Rejects non-PDF and oversized files."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    head = file.file.read(5)
    if head != b"%PDF-":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File must be a PDF")
    stored = f"{uuid.uuid4().hex}.pdf"
    path = _upload_dir() / stored
    size = len(head)
    try:
        with path.open("wb") as out:
            out.write(head)
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is larger than {settings.max_upload_mb} MB"
                    )
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return stored, size


def upload_version(db: Session, user: User, title: str, abstract: str, file: UploadFile) -> Proposal:
    title, abstract = title.strip(), abstract.strip()
    if not title or len(title) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Title must be 1 to 255 characters")
    if not abstract:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Abstract is required")

    stored, size = _save_pdf(file)
    try:
        # Row lock so two uploads at once cannot get the same version number.
        proposal = db.scalar(select(Proposal).where(Proposal.owner_id == user.id).with_for_update())
        if proposal is None:
            proposal = Proposal(owner_id=user.id)
            db.add(proposal)
            db.flush()
        last = db.scalar(select(func.max(ProposalVersion.version_no)).where(ProposalVersion.proposal_id == proposal.id))
        db.add(
            ProposalVersion(
                proposal_id=proposal.id,
                version_no=(last or 0) + 1,
                title=title,
                abstract=abstract,
                original_filename=Path(file.filename or "proposal.pdf").name[:255],
                stored_filename=stored,
                size_bytes=size,
                uploaded_by_id=user.id,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        (_upload_dir() / stored).unlink(missing_ok=True)
        raise HTTPException(status.HTTP_409_CONFLICT, "Another upload happened at the same time, try again")
    except BaseException:
        db.rollback()
        (_upload_dir() / stored).unlink(missing_ok=True)
        raise
    db.refresh(proposal)
    return proposal


def get_version_file(db: Session, user: User, version_id: int) -> tuple[Path, str]:
    version = db.get(ProposalVersion, version_id)
    if version is None or not _can_view(user, version.proposal):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    path = _upload_dir() / version.stored_filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is missing on the server")
    return path, version.original_filename
