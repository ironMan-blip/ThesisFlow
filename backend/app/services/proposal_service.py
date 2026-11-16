import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.milestone import Deliverable, Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import DELETION_DELAY, User
from app.schemas.proposal import MAX_ABSTRACT_CHARS, ProposalOut, ProposalVersionOut
from app.services import progress_service, thesis_service

CHUNK = 1024 * 1024
# Content a PDF viewer could run or hand to the OS: scripts, launch actions, attached files, XFA forms.
ACTIVE_KEYS = {"/JS", "/JavaScript", "/EmbeddedFiles", "/EmbeddedFile", "/XFA", "/RichMedia"}
ACTIVE_ACTIONS = {"/JavaScript", "/Launch", "/ImportData", "/GoToE", "/RichMediaExecute", "/SubmitForm"}
# Bounds the object walk, so a crafted file with millions of tiny objects can't tie up a worker.
MAX_PDF_OBJECTS = 200_000
# Each new version is a stored PDF, so without a cap one student could fill the disk.
MAX_VERSIONS_PER_PHASE = 20


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
        supervisor_contact=thesis and thesis.supervisor and thesis.supervisor.email,
    )
    rows = {v.id: v for v in thesis.versions} if thesis else {}
    for v in out.versions:
        row = rows[v.id]
        if row.delete_by_staff:
            # Scheduled by the supervisor: the page shows it with the reason and who to contact.
            v.delete_pending = not _is_final(db, row)
        else:
            deletable = block is None and _in_current_phase(user, v)
            v.can_request_delete = deletable and row.delete_requested_at is None
            v.delete_pending = deletable and row.delete_requested_at is not None
            v.delete_rejected = row.delete_rejected_at is not None and row.delete_requested_at is None
        if not v.delete_pending:
            v.delete_executes_at = v.delete_reason = None  # lapsed (the version became final)
    return out


def _is_final(db: Session, version: ProposalVersion) -> bool:
    """The version that counts as its phase's submission: the closed phase's final one, or the open phase's latest."""
    return db.scalar(select(Deliverable.id).where(Deliverable.proposal_version_id == version.id)) is not None


def staff_view(db: Session, staff: User, thesis: Thesis, versions: list[ProposalVersionOut]) -> None:
    """Fill in the delete fields a supervisor / co-supervisor sees for one thesis's versions."""
    for v in versions:
        row = db.get(ProposalVersion, v.id)
        final = _is_final(db, row)
        v.delete_pending = row.delete_requested_at is not None and (row.delete_by_staff and not final or _deletable(db, row) is not None)
        v.can_schedule_delete = thesis.supervisor_id == staff.id and not final and row.delete_requested_at is None
        if not v.delete_pending:
            v.delete_executes_at = v.delete_reason = None


def _in_current_phase(user: User, v) -> bool:
    # Only this phase's uploads since it started; earlier phases and semesters are final submissions.
    return v.phase == user.phase and v.created_at >= user.phase_started_at


def _deletable(db: Session, version: ProposalVersion) -> User | None:
    """The version's student while it can still be deleted (their current thesis and phase, uploads still open), else None.

    A submission is final once its phase closes, so a request that isn't approved by then lapses.
    """
    student = version.proposal.thesis.student
    if student is None or student.thesis_id != version.proposal.thesis_id or not _in_current_phase(student, version):
        return None
    return student if _upload_block(db, student)[0] is None else None


def _lock_thesis(db: Session, user: User) -> Thesis | None:
    # Row lock so two uploads on one thesis never race on version numbers.
    return db.scalar(select(Thesis).where(Thesis.id == user.thesis_id).with_for_update())


def _refresh_user(db: Session, user: User) -> None:
    # Re-read under the thesis lock: the semester may have moved on, or the account been deleted, since the request began.
    try:
        db.refresh(user)
    except InvalidRequestError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account no longer exists") from None


def _check_pdf(path: Path) -> None:
    """Refuse anything a PDF reader can't open, an encrypted file (it can't be checked), or one with active content."""
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "PDF must not be password-protected")
        if len(reader.pages) == 0:
            raise ValueError("no pages")
        # Walk everything reachable from the trailer, as a viewer would; escaped and compressed names come out decoded.
        stack, seen = [reader.trailer], set()
        while stack:
            obj = stack.pop()
            if isinstance(obj, IndirectObject):
                if (obj.idnum, obj.generation) in seen:
                    continue
                seen.add((obj.idnum, obj.generation))
                if len(seen) > MAX_PDF_OBJECTS:
                    raise ValueError("too many objects")
                stack.append(obj.get_object())
            elif isinstance(obj, DictionaryObject):
                if ACTIVE_KEYS.intersection(obj) or obj.get("/S") in ACTIVE_ACTIONS:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "PDF must not contain scripts, attached files or interactive forms",
                    )
                stack.extend(dict.values(obj))  # raw values, so references are walked once via `seen`
            elif isinstance(obj, ArrayObject):
                stack.extend(list.__iter__(obj))
    except HTTPException:
        raise
    except Exception:  # pypdf raises many kinds of errors on broken files
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File must be a PDF") from None


def _save_pdf(file: UploadFile) -> tuple[str, int, str]:
    """Stream the upload to disk. Rejects non-PDF and oversized files. Returns name, size and sha256."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    head = file.file.read(5)
    if head != b"%PDF-":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File must be a PDF")
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
                        status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {settings.max_upload_mb} MB"
                    )
                out.write(chunk)
                digest.update(chunk)
        _check_pdf(path)
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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Title must be 1 to 255 characters")
    if not abstract or len(abstract) > MAX_ABSTRACT_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Abstract must be 1 to {MAX_ABSTRACT_CHARS} characters")

    stored, size, sha256 = _save_pdf(file)
    keep_new_file = True
    try:
        thesis = _lock_thesis(db, user)
        # Checked again under the lock: grace may have ended, or the semester moved on, while the file was saved.
        _refresh_user(db, user)
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
                # A version waiting to be deleted is never reused: only the supervisor may stop that delete.
                ProposalVersion.delete_requested_at.is_(None),
            )
        )
        if same is None:
            # Counted under the thesis lock, so parallel uploads can't both slip under the cap.
            if db.scalar(select(func.count()).where(progress_service.phase_uploads(user))) >= MAX_VERSIONS_PER_PHASE:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"You've uploaded {MAX_VERSIONS_PER_PHASE} versions this phase, the most allowed. "
                    "Ask to delete a version you don't need",
                )
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


def request_delete(db: Session, user: User, version_id: int, reason: str) -> ProposalOut:
    """Student: ask to delete one of their versions, with a reason. Their supervisor then approves it, and it runs
    DELETION_DELAY later unless cancelled. Same rule as uploads: current phase, still open; once it closes the
    version is final and kept."""
    version = user.thesis_id and db.scalar(
        select(ProposalVersion).join(Proposal).where(ProposalVersion.id == version_id, Proposal.thesis_id == user.thesis_id)
    )
    if not version:
        # Other students' ids give 404, not 403, so ids are not leaked.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    if version.delete_requested_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This version's deletion is already requested")
    if _deletable(db, version) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This version is a final submission, so it can't be deleted")
    version.delete_requested_at, version.delete_reason = datetime.now(timezone.utc), reason
    version.delete_requested_by_id, version.delete_rejected_at = user.id, None
    db.commit()
    db.refresh(user.thesis)
    return get_mine(db, user)


def schedule_delete(db: Session, staff: User, version_id: int, reason: str) -> None:
    """The thesis's supervisor (not the co-supervisor): delete a version directly. Counts as approved, so it runs
    DELETION_DELAY from now; the supervisor can still cancel it. Never a phase's final version."""
    version = _lock_for(db, version_id)
    if version is None or not thesis_service.can_view(staff, version.proposal.thesis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    if version.proposal.thesis.supervisor_id != staff.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the thesis's supervisor can delete its versions")
    if version.delete_requested_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This version's deletion is already requested")
    if _is_final(db, version):
        raise HTTPException(status.HTTP_409_CONFLICT, "This is the final version of its phase, so it can't be deleted")
    now = datetime.now(timezone.utc)
    version.delete_requested_at = version.delete_approved_at = now
    version.delete_reason, version.delete_requested_by_id, version.delete_rejected_at = reason, staff.id, None
    db.commit()


def _runnable(db: Session, version: ProposalVersion) -> bool:
    # A staff delete never touches a final version; a student's request follows the upload rule (current phase, open).
    return not _is_final(db, version) if version.delete_by_staff else _deletable(db, version) is not None


def _requested() -> Select:
    return select(ProposalVersion).where(ProposalVersion.delete_requested_at.is_not(None))


def count_staff_deletes(db: Session, student: User) -> int:
    """Student badge: their versions the supervisor scheduled for deletion."""
    rows = db.scalars(_requested().join(Proposal).where(Proposal.thesis_id == student.thesis_id)) if student.thesis_id else []
    return sum(v.delete_by_staff and not _is_final(db, v) for v in rows)


def count_delete_requests(db: Session, supervisor: User) -> int:
    """Supervisor badge: students' delete requests on their theses that wait for their decision."""
    rows = db.scalars(
        _requested().join(Proposal).join(Thesis).where(
            Thesis.supervisor_id == supervisor.id, ProposalVersion.delete_approved_at.is_(None)
        )
    )
    return sum(not v.delete_by_staff and _deletable(db, v) is not None for v in rows)


def _supervised(db: Session, supervisor: User, version_id: int) -> ProposalVersion | None:
    """The version, locked, if it belongs to a thesis this faculty member supervises (not co-supervises)."""
    version = _lock_for(db, version_id)
    return version if version is not None and version.proposal.thesis.supervisor_id == supervisor.id else None


def _lock_for(db: Session, version_id: int) -> ProposalVersion | None:
    """The version, re-read after locking its thesis row (uploads lock the same row), or None if it is gone."""
    version = db.get(ProposalVersion, version_id)
    if version is None:
        return None
    db.scalar(select(Thesis).where(Thesis.id == version.proposal.thesis_id).with_for_update())
    db.expire_all()
    return db.get(ProposalVersion, version_id)


def approve_delete(db: Session, supervisor: User, version_id: int) -> None:
    """The thesis's supervisor: approve a student's request. The version is deleted DELETION_DELAY from now unless
    cancelled."""
    version = _supervised(db, supervisor, version_id)
    if version is None or version.delete_requested_at is None or version.delete_approved_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No delete request waiting for approval with that id")
    if _deletable(db, version) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This version became a final submission when its phase closed, so it is kept")
    version.delete_approved_at = datetime.now(timezone.utc)
    db.commit()


def cancel_delete(db: Session, supervisor: User, version_id: int) -> None:
    """The thesis's supervisor only: rejects a request, or cancels an approved / scheduled one any time before it runs."""
    version = _supervised(db, supervisor, version_id)
    if version is None or version.delete_requested_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No delete request with that id")
    # A request the supervisor turns down before approving is shown to the student as rejected.
    version.delete_rejected_at = datetime.now(timezone.utc) if version.delete_approved_at is None else None
    version.delete_requested_at = version.delete_approved_at = version.delete_reason = version.delete_requested_by_id = None
    db.commit()


def _delete_version(db: Session, version: ProposalVersion) -> str:
    """Delete the row and renumber later versions; returns the stored file name for the caller to remove after commit."""
    thesis = version.proposal.thesis
    student = thesis.student if thesis.student and thesis.student.thesis_id == thesis.id else None
    stored, removed_no, proposal_id = version.stored_filename, version.version_no, version.proposal_id
    db.delete(version)
    db.flush()
    _close_gap(db, proposal_id, removed_no)
    if student is None:
        return stored  # archived thesis: no live milestone to update
    if gm := progress_service.group_milestone(db, student):
        progress_service.sync_deliverable(db, gm, student)
    if progress_service.submitted_at(db, student) is None:
        thesis.defer_pending = False  # a deferral needs a P3 submission this semester
    return stored


def run_due_deletions(db: Session, now: datetime | None = None) -> int:
    """Delete every version whose wait is over. Run by the background job in app.main. Returns how many went."""
    cutoff = (now or datetime.now(timezone.utc)) - DELETION_DELAY
    deleted = 0
    for version_id in list(db.scalars(select(ProposalVersion.id).where(ProposalVersion.delete_approved_at <= cutoff))):
        version = _lock_for(db, version_id)
        if version is None or version.delete_approved_at is None or version.delete_approved_at > cutoff:
            db.rollback()  # cancelled meanwhile
            continue
        stored = None
        if _runnable(db, version):
            stored = _delete_version(db, version)
            deleted += 1
        else:
            # It became a final version during the wait (the phase closed, or later versions went): it is kept.
            version.delete_requested_at = version.delete_approved_at = version.delete_reason = None
            version.delete_requested_by_id = None
        db.commit()
        if stored:
            # File goes only after the row is gone, so a failed commit never loses a PDF.
            (_upload_dir() / stored).unlink(missing_ok=True)
    return deleted


def get_version_file(db: Session, user: User, version_id: int) -> tuple[Path, str]:
    version = db.get(ProposalVersion, version_id)
    if version is None or not thesis_service.can_view(user, version.proposal.thesis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    path = _upload_dir() / version.stored_filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is missing on the server")
    return path, version.original_filename
