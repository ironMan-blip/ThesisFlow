from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.milestone import Phase
from app.models.thesis import Thesis


class ProposalVersion(Base):
    """One upload, tracked by its thesis ID. Re-submitting the same PDF, title and abstract moves that version to the top."""

    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("thesis_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"))
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

    thesis: Mapped[Thesis] = relationship(back_populates="versions")
