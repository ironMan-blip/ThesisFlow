import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.milestone import Milestone, Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.user import Role, User
from app.schemas.proposal import ProposalOut

CHUNK = 1024 * 1024


def _upload_dir() -> Path:
    path = Path(settings.upload_dir) / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _can_view(user: User, proposal: Proposal) -> bool:
    # Faculty and coordinator see all proposals (review, F13); students only their own.
    return user.role in (Role.faculty, Role.coordinator) or proposal.owner_id == user.id


def _open_phases(db: Session) -> list[Phase]:
    # Students submit only for phases whose timeline is set and whose grace period hasn't ended.
    now = datetime.now(timezone.utc)
    open_phases = {m.phase for m in db.scalars(select(Milestone)) if now <= m.closes_at}
    return [p for p in Phase if p in open_phases]


def _out(db: Session, proposal: Proposal) -> ProposalOut:
    return ProposalOut(versions=proposal.versions, phases=_open_phases(db))


def get_mine(db: Session, user: User) -> ProposalOut:
    # Before the first upload, use an unsaved empty proposal so the page always gets one shape.
    proposal = db.scalar(select(Proposal).where(Proposal.owner_id == user.id)) or Proposal(owner_id=user.id)
    return _out(db, proposal)


def _lock_mine(db: Session, user: User) -> Proposal | None:
    # Row lock so uploads and deletes for one student never race on version numbers.
    return db.scalar(select(Proposal).where(Proposal.owner_id == user.id).with_for_update())


def _save_pdf(file: UploadFile) -> tuple[str, int, str]:
    """Stream the upload to disk. Rejects non-PDF and oversized files. Returns name, size and sha256."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    head = file.file.read(5)
    if head != b"%PDF-":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File must be a PDF")
    stored = f"{uuid.uuid4().hex}.pdf"
    path = _upload_dir() / stored
    size = len(head)
    digest = hashlib.sha256(head)
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
                digest.update(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return stored, size, digest.hexdigest()


def _close_gap(db: Session, proposal_id: int, removed_no: int) -> None:
    # Later versions move down by one. Two steps through negatives because
    # Postgres checks the (proposal_id, version_no) unique constraint row by row.
    later = (ProposalVersion.proposal_id == proposal_id) & (ProposalVersion.version_no > removed_no)
    db.execute(update(ProposalVersion).where(later).values(version_no=1 - ProposalVersion.version_no))
    db.execute(
        update(ProposalVersion)
        .where(ProposalVersion.proposal_id == proposal_id, ProposalVersion.version_no < 0)
        .values(version_no=-ProposalVersion.version_no)
    )


def upload_version(db: Session, user: User, phase: Phase, title: str, abstract: str, file: UploadFile) -> ProposalOut:
    milestone = db.get(Milestone, phase)
    if milestone is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The {phase.value} timeline is not set yet")
    if datetime.now(timezone.utc) > milestone.closes_at:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The {phase.value} deadline and grace period have passed")
    title, abstract = title.strip(), abstract.strip()
    if not title or len(title) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Title must be 1 to 255 characters")
    if not abstract:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Abstract is required")

    stored, size, sha256 = _save_pdf(file)
    keep_new_file = True
    try:
        proposal = _lock_mine(db, user)
        if proposal is None:
            proposal = Proposal(owner_id=user.id)
            db.add(proposal)
            db.flush()
        last = db.scalar(select(func.max(ProposalVersion.version_no)).where(ProposalVersion.proposal_id == proposal.id))
        fields = dict(
            phase=phase,
            original_filename=Path(file.filename or "proposal.pdf").name[:255],
            uploaded_by_id=user.id,
        )
        # Same PDF with a different title or abstract is a real new version.
        same = db.scalar(
            select(ProposalVersion).where(
                ProposalVersion.proposal_id == proposal.id,
                ProposalVersion.sha256 == sha256,
                ProposalVersion.title == title,
                ProposalVersion.abstract == abstract,
            )
        )
        if same is None:
            db.add(
                ProposalVersion(
                    proposal_id=proposal.id,
                    version_no=(last or 0) + 1,
                    title=title,
                    abstract=abstract,
                    stored_filename=stored,
                    size_bytes=size,
                    sha256=sha256,
                    **fields,
                )
            )
        else:
            # Identical submission already stored: reuse its file and move that version to the top.
            keep_new_file = False
            moved_from = same.version_no
            same.version_no = 0
            db.flush()
            _close_gap(db, proposal.id, moved_from)
            db.execute(
                update(ProposalVersion)
                .where(ProposalVersion.id == same.id)
                .values(version_no=last, created_at=func.now(), **fields)
            )
        db.commit()
    except BaseException as exc:
        db.rollback()
        keep_new_file = False
        if isinstance(exc, IntegrityError):
            raise HTTPException(status.HTTP_409_CONFLICT, "Another upload happened at the same time, try again")
        raise
    finally:
        if not keep_new_file:
            (_upload_dir() / stored).unlink(missing_ok=True)
    db.refresh(proposal)
    return _out(db, proposal)


def delete_version(db: Session, user: User, version_id: int) -> ProposalOut:
    proposal = _lock_mine(db, user)
    # Read after the lock so version_no is current. Other users' ids give 404, not 403, so ids are not leaked.
    version = proposal and db.scalar(
        select(ProposalVersion).where(ProposalVersion.id == version_id, ProposalVersion.proposal_id == proposal.id)
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    stored, removed_no = version.stored_filename, version.version_no
    db.delete(version)
    db.flush()
    _close_gap(db, proposal.id, removed_no)
    db.commit()
    # File goes only after the row is gone, so a failed commit never loses a PDF.
    (_upload_dir() / stored).unlink(missing_ok=True)
    db.refresh(proposal)
    return _out(db, proposal)


def delete_owned(db: Session, user: User) -> list[Path]:
    """Delete the user's proposal and its versions (no commit). Returns their PDFs for the caller to remove after commit."""
    names = list(
        db.scalars(select(ProposalVersion.stored_filename).join(Proposal).where(Proposal.owner_id == user.id))
    )
    # Explicit, not the users FK cascade: proposal_versions.uploaded_by_id would block that.
    db.execute(delete(Proposal).where(Proposal.owner_id == user.id))
    return [_upload_dir() / name for name in names]


def get_version_file(db: Session, user: User, version_id: int) -> tuple[Path, str]:
    version = db.get(ProposalVersion, version_id)
    if version is None or not _can_view(user, version.proposal):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    path = _upload_dir() / version.stored_filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is missing on the server")
    return path, version.original_filename
