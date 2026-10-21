# Import every model here so Alembic autogenerate can see it.
from app.models.user import Role, User

__all__ = ["Role", "User"]
