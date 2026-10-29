# Import every model here so Alembic autogenerate can see it.
from app.models.proposal import Proposal, ProposalVersion
from app.models.user import Role, User

__all__ = ["Proposal", "ProposalVersion", "Role", "User"]
