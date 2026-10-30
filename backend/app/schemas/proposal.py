from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.config import settings
from app.models.milestone import Phase


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


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    versions: list[ProposalVersionOut]  # newest first
    # Upload form options, so the page never hardcodes them: only phases whose timeline is set.
    phases: list[Phase]
    max_upload_mb: int = settings.max_upload_mb

    @model_validator(mode="after")
    def _mark_latest(self):
        if self.versions:
            self.versions[0].is_latest = True
        return self
