# ThesisFlow
A Thesis platform project for CSE470-bracu

Stack: FastAPI + SQLAlchemy + Alembic, PostgreSQL 16 (pgvector), React + Vite + Tailwind. See `470_srs_g7.pdf`.

## Run

Needs Docker only.

```bash
cp .env.example .env          # optional, defaults work for dev
docker compose up --build
docker compose exec backend python -m app.seed   # dev accounts, password: password123
```

- App: http://localhost:5173 (log in as `student@thesisflow.test`, `faculty@thesisflow.test` or `coordinator@thesisflow.test`)
- API docs: http://localhost:8000/docs
- Tests: `docker compose exec backend pytest`

## Layout (MVC)

```
backend/app/
  models/       Model: SQLAlchemy tables
  services/     Model: business rules
  controllers/  Controller: FastAPI routers (check user, call a service, nothing else)
  schemas/      Pydantic request/response shapes
  deps.py       get_current_user, require_roles(...)
backend/alembic/versions/   DB migrations
backend/tests/              pytest
frontend/src/
  pages/        View: one file per page
  components/   View: shared pieces
  api/client.js fetch wrapper (adds JWT)
```

**Rule: logic lives in the backend.** The frontend only shows what the API returns and sends what the user typed. Validation, permissions, status changes, calculations, filtering, sorting, and "can this user do X" checks all go in `services/`. If a page needs a derived value or a flag (e.g. `can_submit`), the API returns it. The frontend never decides it.

## Adding a feature

Example for proposals (F11):

1. `backend/app/models/proposal.py` — table. Import it in `models/__init__.py`.
2. `docker compose exec backend alembic revision --autogenerate -m "proposals"`, check the file, then `alembic upgrade head`.
3. `backend/app/schemas/proposal.py` — request/response models.
4. `backend/app/services/proposal_service.py` — the rules.
5. `backend/app/controllers/proposal_controller.py` — router with `prefix="/api/proposals"`. Add it in `main.py`.
6. `backend/tests/test_proposals.py`.
7. `frontend/src/pages/ProposalPage.jsx` and a route in `App.jsx`.

Protect an endpoint by role:

```python
from app.deps import require_roles
from app.models.user import Role, User

@router.post("")
def create(user: User = Depends(require_roles(Role.coordinator)), db: Session = Depends(get_db)): ...
```

Roles are `student`, `faculty`, `coordinator`. Supervisor and panel member are per-group / per-defense links to a faculty user, not account roles.

## Git workflow

- Branch off `main`: `feature/<short-name>` (e.g. `feature/proposal-upload`).
- Open a PR into `main`. CI runs backend tests and the frontend build.
- Two people adding migrations at once makes two Alembic heads. After pulling, if `alembic heads` shows more than one, set your migration's `down_revision` to the other head.
