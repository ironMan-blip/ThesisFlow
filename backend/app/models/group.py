import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

MIN_MEMBERS = 3
MAX_MEMBERS = 5
INVITE_WINDOW = timedelta(days=3)  # an invitation lapses if nobody answers in this time
INVITE_DAYS = INVITE_WINDOW // timedelta(days=1)


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"  # the leader took it back, or the student joined another group


class Group(Base):
    """A student group of MIN_MEMBERS to MAX_MEMBERS made by its leader. F8 will link it to a thesis."""

    __tablename__ = "student_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    # Handed to the next member when the leader leaves; group_service keeps it set.
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    leader = relationship("User", foreign_keys=[leader_id])
    members = relationship(
        "GroupMember", back_populates="group", order_by="GroupMember.id", cascade="all, delete-orphan", passive_deletes=True
    )
    invitations = relationship("Invitation", back_populates="group", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def is_ready(self) -> bool:
        return len(self.members) >= MIN_MEMBERS


class GroupMember(Base):
    """A student in a group. user_id is unique: a student is in at most one group."""

    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    group = relationship("Group", back_populates="members")
    user = relationship("User")


class Invitation(Base):
    """The leader invites a student; it lapses after INVITE_WINDOW (checked on read, like deletion requests)."""

    __tablename__ = "group_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"))
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"), default=InvitationStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    group = relationship("Group", back_populates="invitations")
    invitee = relationship("User", foreign_keys=[invitee_id])
    invited_by = relationship("User", foreign_keys=[invited_by_id])

    @property
    def expires_at(self) -> datetime:
        return self.created_at + INVITE_WINDOW

    @property
    def is_live(self) -> bool:
        return self.status == InvitationStatus.pending and datetime.now(timezone.utc) < self.expires_at


class StudentProfile(Base):
    """What a student shows in the teammate finder. Interests and skills are comma-separated lowercase tags."""

    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    interests: Mapped[str] = mapped_column(Text, default="", server_default="")
    skills: Mapped[str] = mapped_column(Text, default="", server_default="")
    bio: Mapped[str] = mapped_column(String(500), default="", server_default="")
    # Off means the student is hidden from the finder and can't be invited.
    open_to_invites: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
