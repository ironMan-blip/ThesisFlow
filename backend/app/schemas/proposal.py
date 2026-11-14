from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.config import settings
from app.models.milestone import Phase

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
    can_delete: bool = True  # set by the service: true only while the student could upload it again

    @computed_field
    @property
    def size_label(self) -> str:
        return f"{max(1, round(self.size_bytes / 1024))} KB"

    @computed_field
    @property
    def download_path(self) -> str:
        # Relative to /api, as the frontend client expects.
        return f"/proposals/versions/{self.id}/file"


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

    @model_validator(mode="after")
    def _mark_latest(self):
        if self.versions:
            self.versions[0].is_latest = True
        return self
