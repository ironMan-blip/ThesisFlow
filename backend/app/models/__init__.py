# Import every model here so Alembic autogenerate can see it.
from app.models.meeting import Meeting, MeetingTask
from app.models.milestone import Deliverable, GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.semester import Semester
from app.models.thesis import Thesis, ThesisStatus, TitleChange
from app.models.user import Role, User
from app.models.group import Group, GroupMember, Invitation, InvitationStatus, StudentProfile

__all__ = [
    "Deliverable", "GroupMilestone", "Meeting", "MeetingTask", "MilestoneTemplate", "Phase", "Proposal", "ProposalVersion", "Role", "Semester", "Thesis", "ThesisStatus", "TitleChange", "User",
]
