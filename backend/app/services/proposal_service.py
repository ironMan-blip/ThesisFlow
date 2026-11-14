import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.milestone import Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import User
from app.schemas.proposal import MAX_ABSTRACT_CHARS, ProposalOut
from app.services import progress_service, thesis_service

CHUNK = 1024 * 1024


def _upload_dir() -> Path:
    path = Path(settings.upload_dir) / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_block(db: Session, user: User) -> tuple[str | None, progress_service.Standing]:
    """Why this student can't upload right now (None means they can), and their standing."""
    s = progress_service.standing(db, user)
    thesis = user.thesis
    if user.phase is None:
        return "Your thesis is complete", s
    if s.frozen:
        if user.restart_pending or user.restart_approved:
            return f"{s.frozen_reason}, so your account is frozen until you start fresh at P1", s
        return f"{s.frozen_reason}, so your account is frozen. Ask to restart at P1 on the Thesis page", s
    if thesis is None:
        return "Form a thesis group first: choose a supervisor on the Thesis page", s
    if thesis.status != ThesisStatus.active:
        return "Your supervisor has not accepted your thesis group yet", s
    if user.phase == Phase.P1 and not thesis.p1_registered:
        if progress_service.registration_open(db):
            return "Register your group for P1 on the Thesis page first", s
        return "Your group isn't registered for P1, and P1 registration is closed, so wait for next semester", s
    if s.template is None:
        return f"The {user.phase.value} timeline is not set yet", s
    if datetime.now(timezone.utc) > s.closes_at:
        return f"The {user.phase.value} deadline and grace period have passed", s
    return None, s


def get_mine(db: Session, user: User) -> ProposalOut:
    block, s = _upload_block(db, user)
    thesis = user.thesis
    out = ProposalOut(
        versions=thesis.versions if thesis else [],
        thesis_code=thesis and thesis.code,
        phase=user.phase,
        upload_block=block,
        freeze_at=s.closes_at if block is None and s.submitted_at is None and datetime.now(timezone.utc) > s.due_at else None,
    )
    for v in out.versions:
        # A submission is final once its phase closes, or once it belongs to an earlier phase or semester.
        v.can_delete = block is None and v.phase == user.phase and v.created_at >= user.phase_started_at
    return out


def _lock_thesis(db: Session, user: User) -> Thesis | None:
    # Row lock so uploads and deletes on one thesis never race on version numbers.
    return db.scalar(select(Thesis).where(Thesis.id == user.thesis_id).with_for_update())


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


def upload_version(db: Session, user: User, title: str, abstract: str, file: UploadFile) -> ProposalOut:
    # Uploads always go to the student's current phase, under their thesis ID.
    if block := _upload_block(db, user)[0]:
        raise HTTPException(status.HTTP_409_CONFLICT, block)
    title, abstract = title.strip(), abstract.strip()
    if not title or len(title) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Title must be 1 to 255 characters")
    if not abstract or len(abstract) > MAX_ABSTRACT_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Abstract must be 1 to {MAX_ABSTRACT_CHARS} characters")

    stored, size, sha256 = _save_pdf(file)
    keep_new_file = True
    try:
        thesis = _lock_thesis(db, user)
        # Checked again under the lock: grace may have ended, or the semester moved on, while the file was saved.
        db.refresh(user)
        if block := _upload_block(db, user)[0]:
            raise HTTPException(status.HTTP_409_CONFLICT, block)
        proposal = thesis.proposal
        if proposal is None:
            proposal = Proposal(thesis_id=thesis.id)
            db.add(proposal)
            db.flush()
        gm = progress_service.group_milestone(db, user, create=True)
        last = db.scalar(select(func.max(ProposalVersion.version_no)).where(ProposalVersion.proposal_id == proposal.id))
        fields = dict(
            phase=user.phase,
            original_filename=Path(file.filename or "proposal.pdf").name[:255],
            uploaded_by_id=user.id,
        )
        # Same PDF with a different title or abstract is a real new version. Only this phase's uploads are
        # reused, so a final submission from an earlier phase or semester is never rewritten.
        same = db.scalar(
            select(ProposalVersion).where(
                progress_service.phase_uploads(user),
                ProposalVersion.sha256 == sha256,
                ProposalVersion.title == title,
                ProposalVersion.abstract == abstract,
            )
        )
        if same is None:
            version = ProposalVersion(
                proposal_id=proposal.id,
                version_no=(last or 0) + 1,
                title=title,
                abstract=abstract,
                stored_filename=stored,
                size_bytes=size,
                sha256=sha256,
                **fields,
            )
            db.add(version)
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
                .values(version_no=last, created_at=datetime.now(timezone.utc), **fields)
            )
        progress_service.sync_deliverable(db, gm, user)
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
    db.refresh(thesis)
    return get_mine(db, user)


def delete_version(db: Session, user: User, version_id: int) -> ProposalOut:
    thesis = user.thesis_id and _lock_thesis(db, user)
    # Read after the lock so version_no is current. Other users' ids give 404, not 403, so ids are not leaked.
    version = thesis and db.scalar(
        select(ProposalVersion)
        .join(Proposal)
        .where(ProposalVersion.id == version_id, Proposal.thesis_id == thesis.id)
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    if not next(v.can_delete for v in get_mine(db, user).versions if v.id == version.id):
        # Submissions are final once the phase closes; removing one could also turn it into a missed deadline.
        raise HTTPException(status.HTTP_409_CONFLICT, "This version is a final submission, so it can't be removed")
    stored, removed_no = version.stored_filename, version.version_no
    db.delete(version)
    db.flush()
    _close_gap(db, version.proposal_id, removed_no)
    if gm := progress_service.group_milestone(db, user):
        progress_service.sync_deliverable(db, gm, user)
    if progress_service.submitted_at(db, user) is None:
        thesis.defer_pending = False  # a deferral needs a P3 submission this semester
    db.commit()
    # File goes only after the row is gone, so a failed commit never loses a PDF.
    (_upload_dir() / stored).unlink(missing_ok=True)
    db.refresh(thesis)
    return get_mine(db, user)


def get_version_file(db: Session, user: User, version_id: int) -> tuple[Path, str]:
    version = db.get(ProposalVersion, version_id)
    if version is None or not thesis_service.can_view(user, version.proposal.thesis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    path = _upload_dir() / version.stored_filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is missing on the server")
    return path, version.original_filename
