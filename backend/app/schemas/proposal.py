from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProposalVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    title: str
    abstract: str
    original_filename: str
    size_bytes: int
    created_at: datetime


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime
    versions: list[ProposalVersionOut]  # newest first
