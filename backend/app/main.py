from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.controllers import auth_controller, milestone_controller, proposal_controller
from app.database import SessionLocal
from app.services import auth_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        auth_service.ensure_admin(db)
    yield


app = FastAPI(title="ThesisFlow API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register each feature's router here.
app.include_router(auth_controller.router)
app.include_router(proposal_controller.router)
app.include_router(milestone_controller.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
