from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.milestone import Phase


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    # shortcut: owned by the uploading student until groups (F6) exist; switch to group_id then.
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["ProposalVersion"]] = relationship(
        back_populates="proposal", order_by="ProposalVersion.version_no.desc()"
    )


class ProposalVersion(Base):
    """One upload. Versions are never edited; the owning student may delete one."""

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
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    proposal: Mapped[Proposal] = relationship(back_populates="versions")
