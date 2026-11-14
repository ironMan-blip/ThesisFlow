from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers import account_controller, auth_controller, milestone_controller, proposal_controller, thesis_controller
from app.config import settings
from app.database import SessionLocal
from app.rate_limit import rate_limit
from app.services import auth_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        auth_service.ensure_admin(db)
    yield


app = FastAPI(title="ThesisFlow API", lifespan=lifespan)
app.middleware("http")(rate_limit)

@app.middleware("http")
async def limit_body(request: Request, call_next):
    # The server reads the whole body to disk before the upload's own size check runs, so refuse huge ones up front.
    # shortcut: trusts Content-Length (browsers always send it); chunked bodies are still only checked by the service.
    size = request.headers.get("content-length", "")
    # 1 MB on top of the PDF limit for the title, abstract and form overhead.
    if size.isdigit() and int(size) > (settings.max_upload_mb + 1) * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": f"Upload is larger than {settings.max_upload_mb} MB"})
    return await call_next(request)

# No CORS: the browser only talks to the Vite dev server, which proxies /api here.
# Register each feature's router here.
app.include_router(auth_controller.router)
app.include_router(account_controller.router)
app.include_router(proposal_controller.router)
app.include_router(milestone_controller.router)
app.include_router(thesis_controller.router)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # One readable sentence instead of pydantic's error list, so the UI can show it as-is.
    err = exc.errors()[0]
    field = err["loc"][-1] if err["loc"] else "request"
    msg = err["msg"].removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"detail": f"{field}: {msg}"})
