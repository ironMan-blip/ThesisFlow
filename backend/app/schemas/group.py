from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.group import INVITE_DAYS, MAX_MEMBERS, MIN_MEMBERS
from app.schemas.thesis import PersonOut

MAX_TAGS = 10
MAX_TAG_CHARS = 30
MAX_BIO_CHARS = 500


class GroupCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=60)


class InviteIn(BaseModel):
    student_id: int


class ProfileIn(BaseModel):
    interests: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    skills: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    bio: str = Field("", max_length=MAX_BIO_CHARS)
    open_to_invites: bool = True

    @field_validator("interests", "skills")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        tags = list(dict.fromkeys(t.strip().lower() for t in v if t.strip()))
        if any(len(t) > MAX_TAG_CHARS or "," in t for t in tags):
            raise ValueError(f"Each tag must be {MAX_TAG_CHARS} characters or fewer, with no commas")
        return tags


class ProfileOut(ProfileIn):
    max_tags: int = MAX_TAGS
    max_tag_chars: int = MAX_TAG_CHARS
    max_bio_chars: int = MAX_BIO_CHARS


class GroupOut(BaseModel):
    id: int
    name: str
    leader: PersonOut | None
    members: list[PersonOut]
    is_ready: bool  # has at least MIN_MEMBERS
    members_needed: int  # how many more to reach MIN_MEMBERS
    created_at: datetime


class InvitationOut(BaseModel):
    id: int
    group_id: int
    group_name: str
    member_count: int
    invitee: PersonOut
    invited_by: PersonOut | None
    created_at: datetime
    expires_at: datetime


class MyGroupOut(BaseModel):
    group: GroupOut | None
    is_leader: bool
    can_create: bool
    can_invite: bool  # leader with a free spot (members + live invitations < max)
    can_leave: bool
    open_slots: int
    sent_invitations: list[InvitationOut]  # live ones, for the group's members
    received_invitations: list[InvitationOut]  # live ones, for a student without a group
    min_members: int = MIN_MEMBERS
    max_members: int = MAX_MEMBERS
    invite_days: int = INVITE_DAYS


class TeammateOut(PersonOut):
    interests: list[str]
    skills: list[str]
    bio: str
    invited: bool  # the requester's group has a live invitation out to them
    can_invite: bool
