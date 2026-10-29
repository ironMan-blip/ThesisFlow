from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class ProposalVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
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

    id: int | None  # None until the first upload
    owner_id: int
    created_at: datetime | None
    versions: list[ProposalVersionOut]  # newest first

    @model_validator(mode="after")
    def _mark_latest(self):
        if self.versions:
            self.versions[0].is_latest = True
        return self
