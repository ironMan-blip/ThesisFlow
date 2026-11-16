from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.milestone import Phase
from app.models.thesis import Thesis
from app.models.user import DELETION_DELAY


class Proposal(Base):
    """A thesis group's proposal: one per thesis, made on its first upload. Holds every version."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    thesis: Mapped[Thesis] = relationship(back_populates="proposal")
    versions = relationship(
        "ProposalVersion", back_populates="proposal", order_by="ProposalVersion.version_no.desc()"
    )


class ProposalVersion(Base):
    """One upload of a proposal. Re-submitting the same PDF, title and abstract moves that version to the top."""

    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    # Which deadline (F12) this upload is submitted for.
    phase: Mapped[Phase] = mapped_column(Enum(Phase, name="phase"), server_default=Phase.P1.value)
    title: Mapped[str] = mapped_column(String(255))
    abstract: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Null for rows uploaded before hashing existed.
    sha256: Mapped[str | None] = mapped_column(String(64))
    # Null once the uploader's account is deleted; the version itself is kept.
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # App clock, not the database's: it is compared with phase_started_at, also set by the app.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    # Set when the student asks to delete this version (SRS F11 keeps old versions otherwise). The thesis's supervisor
    # approves it; it then runs DELETION_DELAY later unless the supervisor cancels it or the phase closes first.
    delete_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delete_reason: Mapped[str | None] = mapped_column(Text)
    # Set when the supervisor approves the request: only then does the DELETION_DELAY clock start.
    delete_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who asked: the student, or the supervisor scheduling it directly (approved at once).
    delete_requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Set when the supervisor rejects the student's request, so the student sees the answer; cleared on a new request.
    delete_rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proposal: Mapped[Proposal] = relationship(back_populates="versions")

    @property
    def delete_by_staff(self) -> bool:
        # A deleted staff account leaves None, which still isn't the student. A deleted student's own request lapses.
        return self.delete_requested_at is not None and self.delete_requested_by_id != self.proposal.thesis.student_id

    @property
    def delete_executes_at(self) -> datetime | None:
        return self.delete_approved_at and self.delete_approved_at + DELETION_DELAY
