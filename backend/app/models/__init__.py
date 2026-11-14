# Import every model here so Alembic autogenerate can see it.
from app.models.milestone import Milestone, Phase
from app.models.proposal import ProposalVersion
from app.models.semester import Semester
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User

__all__ = ["Milestone", "Phase", "ProposalVersion", "Role", "Semester", "Thesis", "ThesisStatus", "User"]
