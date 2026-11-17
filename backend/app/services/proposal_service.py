import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session

from app import virus_scan
from app.config import settings
from app.models.milestone import Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.thesis import TITLE_CHANGE_WINDOW, Thesis, ThesisStatus, TitleChange
from app.models.user import User
from app.schemas.proposal import MAX_ABSTRACT_CHARS, ProposalOut, TitleChangeOut
from app.services import progress_service, thesis_service

CHUNK = 1024 * 1024
# Content a PDF viewer could run or hand to the OS: scripts, launch actions, attached files, XFA forms.
ACTIVE_KEYS = {"/JS", "/JavaScript", "/EmbeddedFiles", "/EmbeddedFile", "/XFA", "/RichMedia"}
ACTIVE_ACTIONS = {"/JavaScript", "/Launch", "/ImportData", "/GoToE", "/RichMediaExecute", "/SubmitForm"}
# Bounds the object walk, so a crafted file with millions of tiny objects can't tie up a worker.
MAX_PDF_OBJECTS = 200_000
log = logging.getLogger(__name__)
# Each new version is a stored PDF and versions are never deleted (SRS F11), so without a cap one student could fill the disk.
MAX_VERSIONS_PER_PHASE = 20


def _upload_dir() -> Path:
    path = Path(settings.upload_dir) / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_block(
    db: Session, user: User, s: progress_service.Standing | None = None
) -> tuple[str | None, progress_service.Standing]:
    """Why this student can't upload right now (None means they can), and their standing (pass it if known)."""
    s = s or progress_service.standing(db, user)
    thesis = user.thesis
    if user.phase is None:
        return "Your thesis is complete", s
    if s.frozen:
        if user.restart_pending or user.restart_approved:
            return f"{s.frozen_reason}, so your account is frozen until you start fresh at P1", s
        return f"{s.frozen_reason}, so your account is frozen. Ask to restart at P1 on the Thesis page", s
    if thesis is None:
        return "Form a thesis group first: choose a supervisor on the Thesis page", s
    if thesis.status == ThesisStatus.pending:
        return "Your supervisor has not accepted your thesis group yet", s
    if thesis.status != ThesisStatus.active or (user.phase == Phase.P1 and not thesis.p1_registered):
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
    latest = thesis.title_changes[0] if thesis and thesis.title_changes else None
    return ProposalOut(
        versions=thesis.versions if thesis else [],
        thesis_code=thesis and thesis.code,
        phase=user.phase,
        upload_block=block,
        freeze_at=s.closes_at if block is None and s.submitted_at is None and datetime.now(timezone.utc) > s.due_at else None,
        title=thesis and thesis.title,
        abstract=thesis and thesis.abstract,
        title_change=latest and TitleChangeOut.model_validate(latest),
        can_request_title_change=thesis is not None and _title_change_block(thesis) is None,
    )


def _clean(title: str, abstract: str) -> tuple[str, str]:
    # Browsers send form uploads with CRLF but JSON (title change) with LF; one form, so the exact-match check holds.
    title, abstract = (s.replace("\r\n", "\n").replace("\r", "\n").strip() for s in (title, abstract))
    if not title or len(title) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Title must be 1 to 255 characters")
    if not abstract or len(abstract) > MAX_ABSTRACT_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Abstract must be 1 to {MAX_ABSTRACT_CHARS} characters")
    return title, abstract


def _check_title(thesis: Thesis | None, title: str, abstract: str) -> None:
    # The first upload sets them (thesis.title is None until then); after that only an approved change moves them.
    if thesis is None or thesis.title is None:
        return
    wrong = [name for name, given, kept in (("title", title, thesis.title), ("abstract", abstract, thesis.abstract)) if given != kept]
    if wrong:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Wrong {' and '.join(wrong)}: uploads must use your thesis's {' and '.join(wrong)} exactly. "
            "To change them, request it from your supervisor on this page (allowed once)",
        )


def _title_change_block(thesis: Thesis) -> str | None:
    """Why this thesis can't request a title and abstract change now (None means it can)."""
    if thesis.title is None:
        return "Upload your first version first: it sets your title and abstract"
    if thesis.status != ThesisStatus.active:
        return "Only an active thesis can change its title and abstract"
    if thesis.supervisor_id is None:
        return "Your thesis has no supervisor to approve a change"
    statuses = {c.status for c in thesis.title_changes}
    if "approved" in statuses:
        return "You've already used your one title and abstract change"
    if "pending" in statuses:
        return "Your change request is still waiting for your supervisor"
    return None


def _lock_thesis(db: Session, user: User) -> Thesis | None:
    # Row lock so two uploads on one thesis never race on version numbers.
    return db.scalar(select(Thesis).where(Thesis.id == user.thesis_id).with_for_update())


def _refresh_user(db: Session, user: User) -> None:
    # Re-read under the thesis lock: the semester may have moved on, or the account been deleted, since the request began.
    try:
        db.refresh(user)
    except InvalidRequestError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account no longer exists") from None


def _scan(path: Path) -> None:
    # Fails closed: with no scanner, nothing is stored unchecked.
    try:
        found = virus_scan.scan(path)
    except virus_scan.ScannerUnavailable as exc:
        log.error("Virus scan unavailable, upload refused: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The virus scanner isn't ready, so uploads are paused. Try again in a few minutes",
            headers={"Retry-After": "30"},
        ) from None
    if found:
        log.warning("Upload refused, ClamAV found %s", found)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"This file contains malware ({found}), so it wasn't stored"
        )


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
        _scan(path)  # before parsing, so pypdf never reads a known-bad file
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
    title, abstract = _clean(title, abstract)
    _check_title(user.thesis, title, abstract)  # before storing the file, so a wrong title fails fast

    stored, size, sha256 = _save_pdf(file)
    keep_new_file = True
    try:
        thesis = _lock_thesis(db, user)
        # Checked again under the lock: grace may have ended, or the semester moved on, while the file was saved.
        _refresh_user(db, user)
        if block := _upload_block(db, user)[0]:
            raise HTTPException(status.HTTP_409_CONFLICT, block)
        _check_title(thesis, title, abstract)  # again under the lock: a change may have been approved meanwhile
        if thesis.title is None:
            thesis.title, thesis.abstract = title, abstract
        proposal = thesis.proposal
        if proposal is None:
            proposal = Proposal(thesis_id=thesis.id)
            db.add(proposal)
            db.flush()
        gm = progress_service.group_milestone(db, user, create=True)
        last = db.scalar(select(func.max(ProposalVersion.version_no)).where(ProposalVersion.proposal_id == proposal.id))
        name = Path(file.filename or "").name[:255]
        fields = dict(
            phase=user.phase,
            # "..", "." or only dots and spaces is no file name: fall back to a plain one.
            original_filename=name if name.strip(". ") else "proposal.pdf",
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
            # Counted under the thesis lock, so parallel uploads can't both slip under the cap.
            if db.scalar(select(func.count()).where(progress_service.phase_uploads(user))) >= MAX_VERSIONS_PER_PHASE:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"You've uploaded {MAX_VERSIONS_PER_PHASE} versions this phase, the most allowed. "
                    "Re-upload one of them unchanged to make it the latest again",
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


def request_title_change(db: Session, user: User, title: str, abstract: str) -> ProposalOut:
    """Student: ask the supervisor to change the thesis title and abstract. Only one change is ever approved, and the
    supervisor has TITLE_CHANGE_WINDOW to accept it."""
    title, abstract = _clean(title, abstract)
    thesis = _lock_thesis(db, user)
    if thesis is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Form a thesis group first")
    if block := _title_change_block(thesis):
        raise HTTPException(status.HTTP_409_CONFLICT, block)
    if (title, abstract) == (thesis.title, thesis.abstract):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That is already your title and abstract")
    db.add(TitleChange(thesis_id=thesis.id, title=title, abstract=abstract))
    db.commit()
    db.refresh(thesis)
    return get_mine(db, user)


def decide_title_change(db: Session, supervisor: User, change_id: int, approve: bool) -> None:
    """The thesis's supervisor (not the co-supervisor): accept or reject a waiting change request."""
    change = db.get(TitleChange, change_id)
    thesis = change and db.scalar(select(Thesis).where(Thesis.id == change.thesis_id).with_for_update())
    if thesis is None or thesis.supervisor_id != supervisor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No title change request with that id")
    db.refresh(change)
    if change.status == "expired":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"This request expired: it had to be accepted within {TITLE_CHANGE_WINDOW.days} days. The group can ask again"
        )
    if change.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is already decided")
    if approve and thesis.status != ThesisStatus.active:
        # Same rule as asking: a dropped or completed thesis keeps its title. Rejecting still clears the request.
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an active thesis can change its title and abstract")
    change.decided_at, change.approved = datetime.now(timezone.utc), approve
    if approve:
        thesis.title, thesis.abstract = change.title, change.abstract
    db.commit()


def count_title_changes(db: Session, supervisor: User) -> int:
    """Supervisor badge: change requests waiting for their decision. Polled every 10s, so counted in SQL."""
    return db.scalar(
        select(func.count(TitleChange.id)).join(Thesis).where(
            Thesis.supervisor_id == supervisor.id,
            TitleChange.decided_at.is_(None),
            TitleChange.created_at > datetime.now(timezone.utc) - TITLE_CHANGE_WINDOW,
        )
    )


def get_version_file(db: Session, user: User, version_id: int) -> tuple[Path, str]:
    version = db.get(ProposalVersion, version_id)
    if version is None or not thesis_service.can_view(user, version.proposal.thesis):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    path = _upload_dir() / version.stored_filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is missing on the server")
    return path, version.original_filename
