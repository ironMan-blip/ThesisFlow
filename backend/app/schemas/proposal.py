from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.config import settings
from app.models.milestone import Phase
from app.models.thesis import TITLE_CHANGE_WINDOW

MAX_ABSTRACT_CHARS = 5000


class ProposalVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    phase: Phase
    title: str
    abstract: str
    original_filename: str
    size_bytes: int
    created_at: datetime
    is_latest: bool = False  # set by ProposalOut

    @computed_field
    @property
    def size_label(self) -> str:
        return f"{max(1, round(self.size_bytes / 1024))} KB"

    @computed_field
    @property
    def download_path(self) -> str:
        # Relative to /api, as the frontend client expects.
        return f"/proposals/versions/{self.id}/file"


class TitleChangeIn(BaseModel):
    title: str
    abstract: str  # both checked like an upload's (proposal_service._clean)


class TitleChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    abstract: str
    created_at: datetime
    expires_at: datetime  # the supervisor must accept before this
    status: Literal["pending", "approved", "rejected", "expired"]


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    versions: list[ProposalVersionOut]  # newest first, all under one thesis ID
    thesis_code: str | None  # None until the supervisor accepts the thesis group
    phase: Phase | None  # the student's current phase; uploads always go to it
    upload_block: str | None = None  # why uploading is closed right now; None means open
    # In grace with nothing submitted: the account freezes at this time unless they upload.
    freeze_at: datetime | None = None
    max_upload_mb: int = settings.max_upload_mb
    max_abstract_chars: int = MAX_ABSTRACT_CHARS
    # The thesis's title and abstract: set by the first upload, and every later upload must match them.
    title: str | None = None
    abstract: str | None = None
    title_change: TitleChangeOut | None = None  # the latest change request, if any
    can_request_title_change: bool = False  # the one approved change isn't used and no request is waiting
    title_change_days: int = TITLE_CHANGE_WINDOW.days

    @model_validator(mode="after")
    def _mark_latest(self):
        if self.versions:
            self.versions[0].is_latest = True
        return self
