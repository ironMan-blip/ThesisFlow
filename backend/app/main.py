import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, OperationalError

from app.controllers import account_controller, auth_controller, milestone_controller, proposal_controller, thesis_controller
from app.config import settings
from app.database import SessionLocal
from app.rate_limit import rate_limit
from app.security import decode_access_token
from app.services import auth_service

# Only uploads are bigger than this, and only signed-in students upload.
ANONYMOUS_BODY_LIMIT = 64 * 1024


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
    # FastAPI parses the body before auth runs, so a chunked body (no Content-Length) could stream forever
    # anonymously. Browsers always send Content-Length, so refuse chunked bodies outright.
    if "transfer-encoding" in request.headers:
        return JSONResponse(status_code=411, content={"detail": "Content-Length is required"})
    size = request.headers.get("content-length", "")
    # 1 MB on top of the PDF limit for the title, abstract and form overhead.
    if size.isdigit() and int(size) > (settings.max_upload_mb + 1) * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": f"Upload is larger than {settings.max_upload_mb} MB"})
    # Auth runs after the body is parsed, so check the token here before anyone can make the server spool a big upload.
    if size.isdigit() and int(size) > ANONYMOUS_BODY_LIMIT:
        auth = request.headers.get("authorization", "")
        if not (auth.startswith("Bearer ") and decode_access_token(auth[7:])):
            return JSONResponse(status_code=401, content={"detail": "Sign in to upload"})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Registered last, so it runs outermost and also covers the 411/413/429 replies above.
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # an uploaded "PDF" is never run as HTML or script
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        # API replies are JSON or PDF downloads, never pages. Not on /docs: Swagger UI needs its CDN scripts.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response

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


@app.exception_handler(DataError)
async def bad_value(_: Request, exc: DataError):
    # Postgres refused a value no schema catches: a NUL character in text, or an id past the integer range.
    logging.getLogger(__name__).info("Database refused a value: %s", exc.orig)
    return JSONResponse(status_code=422, content={"detail": "request: contains a value the server can't store"})


@app.exception_handler(OperationalError)
async def database_unavailable(_: Request, exc: OperationalError):
    # Postgres down or restarting: say so (503) instead of a bare 500, so the UI shows a clear message.
    logging.getLogger(__name__).error("Database unavailable: %s", exc.orig)
    return JSONResponse(
        status_code=503,
        content={"detail": "ThesisFlow can't reach its database right now. Try again in a moment."},
        headers={"Retry-After": "5"},
    )
