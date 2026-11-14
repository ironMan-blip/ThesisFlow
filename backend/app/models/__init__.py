# Import every model here so Alembic autogenerate can see it.
from app.models.milestone import Deliverable, GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.semester import Semester
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User

__all__ = [
    "Deliverable", "GroupMilestone", "MilestoneTemplate", "Phase", "Proposal", "ProposalVersion", "Role", "Semester", "Thesis", "ThesisStatus", "User",
]
