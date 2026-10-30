# ThesisFlow
A Thesis platform project for CSE470-bracu

Stack: FastAPI + SQLAlchemy + Alembic, PostgreSQL 16 (pgvector), React + Vite + Tailwind. See `470_srs_g7.pdf`.

## Features so far

- Accounts: register / log in (JWT), password strength check, role-based tools on the dashboard.
- Faculty approval: new faculty wait for coordinator approval.
- Account deletion: request + coordinator approval, 48-hour lapse.
- Deadlines: coordinator sets a deadline per phase (phase deadlines must stay in order: none before an earlier phase's or after a later one's); students see a countdown, on-time / late status and late days.
- Proposals: students upload PDF versions (max `MAX_UPLOAD_MB`, default 20 MB) and delete them. Re-uploading an identical file (same sha256) moves it to the latest version instead of storing a copy.

## How it works

```mermaid
flowchart TB
    subgraph AUTH["① LOGIN · POST /api/auth/login"]
        direction LR
        L1(["🔑 <b>Login page</b><br/>email + password"]) --> L2["🛡️ <b>Verify</b><br/>Argon2 hash check"]
        L2 --> L3{"Faculty not<br/>approved yet?"}
        L3 -- yes --> L4(["⛔ <b>403</b><br/>wait for coordinator"])
        L3 -- no --> L5["🎟️ <b>JWT issued</b> · HS256<br/>saved in localStorage"]
        L5 --> L6["👤 <b>GET /api/auth/me</b><br/>user · role · tools"]
        L6 --> L7(["🧭 <b>Dashboard</b><br/>only that role's tools"])
    end

    AUTH -- "every request: Bearer JWT → require_roles(...)" --> DB

    DB[("🗄️ <b>PostgreSQL 16</b><br/>users · milestones<br/>proposals · proposal_versions")]

    DB --> STU & FAC & COO

    subgraph STU["🎓 STUDENT"]
        direction LR
        S1["📄 <b>Upload proposal</b><br/>PDF · title · abstract<br/>max MAX_UPLOAD_MB"] --> S2{"Same SHA-256<br/>already uploaded?"}
        S2 -- yes --> S3["⏫ Move to<br/>latest version"]
        S2 -- no --> S4["🆕 New version<br/>view · download · delete"]
        S5["⏳ <b>Deadlines</b><br/>countdown · late days"]
        S6["🗑️ <b>Request deletion</b><br/>coordinator decides"]
    end

    subgraph FAC["🧑‍🏫 FACULTY"]
        direction LR
        F1["⏳ <b>Deadlines</b><br/>see phase dates"]
        F2["🗑️ <b>Request deletion</b><br/>coordinator decides"]
    end

    subgraph COO["🛠️ COORDINATOR"]
        direction LR
        C1["📅 <b>Set deadlines</b><br/>P1 → P2 → P3"] --> C2{"In order?"}
        C2 -- no --> C3(["⛔ 409"])
        C2 -- yes --> C4["✅ Saved"]
        C5["✔️ <b>Faculty requests</b><br/>approve / reject"]
        C6["🗑️ <b>Deletion requests</b><br/>approve / reject<br/>lapses after 48h"]
    end

    classDef io fill:#e8f7ec,stroke:#3a9d5d,color:#1d4d2c
    classDef step fill:#ffffff,stroke:#555,color:#222
    classDef core fill:#efe9fb,stroke:#7a4fcf,color:#3b2470
    classDef decide fill:#fdf1c7,stroke:#d9a400,color:#5c4500
    classDef stop fill:#fde8e8,stroke:#c94a4a,color:#6b1f1f
    classDef store fill:#dde8ff,stroke:#3f63c9,color:#1f3470

    class L1,L7 io
    class L2,L6,S3,S4,C4 step
    class L5,S1,S5,S6,F1,F2,C1,C5,C6 core
    class L3,S2,C2 decide
    class L4,C3 stop
    class DB store
    style AUTH fill:#f7f8fa,stroke:#999
    style STU fill:#f4f7ff,stroke:#3f63c9
    style FAC fill:#fff8ec,stroke:#c48a1a
    style COO fill:#f1faf3,stroke:#2f8a4f
```

## Run

Needs Docker only.

```bash
cp .env.example .env          # optional, defaults work for dev
docker compose up --build
docker compose exec backend python -m app.seed   # dev student + faculty, password: password123
```

- App: http://localhost:5173 (log in as `student@thesisflow.test` or `faculty@thesisflow.test`; coordinator is `ADMIN_EMAIL` / `ADMIN_PASSWORD`, default `coordinator@thesisflow.test` / `password123`)
- Sign-up: students can log in right away. Faculty wait for the coordinator to approve them under "Faculty requests". There is no coordinator sign-up; the one coordinator account is created/updated from `ADMIN_EMAIL` / `ADMIN_PASSWORD` when the backend starts.
- Account deletion: students and faculty request it under "Account". The coordinator approves or rejects it under "Deletion requests"; a request not approved within 48 hours lapses and the account is kept. The coordinator account cannot be deleted.
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
  pages/        View: one file per page (RequestsPage = faculty + deletion requests)
  components/   View: Layout (auth guard + nav), ui.jsx (Logo, PageHeader, Alerts)
  api/client.js fetch wrapper (adds JWT)
  useAction.js  busy / error / success state for a page's API calls
  tools.jsx     nav + dashboard entry for each tool key the API returns in user.tools
  format.js     shared display formatting
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
