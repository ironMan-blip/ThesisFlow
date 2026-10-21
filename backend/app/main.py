from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.controllers import auth_controller

app = FastAPI(title="ThesisFlow API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register each feature's router here.
app.include_router(auth_controller.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
