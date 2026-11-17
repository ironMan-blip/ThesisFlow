import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, OperationalError
from starlette.concurrency import run_in_threadpool

from app.controllers import account_controller, auth_controller, group_controller, meeting_controller, milestone_controller, proposal_controller, thesis_controller
from app import virus_scan
from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import user_for_token
from app.rate_limit import rate_limit
from app.services import account_service, auth_service, proposal_service

# Only uploads are bigger than this, and only signed-in students upload.
ANONYMOUS_BODY_LIMIT = 64 * 1024


# Scheduled deletes run at most this long after their 7-day wait ends.
DELETION_CHECK_SECONDS = 300
# clamd's first start (signature download) can take minutes: retry every 10 s for up to 10 minutes.
SCANNER_WARM_UP_TRIES, SCANNER_WARM_UP_RETRY_SECONDS = 60, 10
log = logging.getLogger(__name__)


def _run_due_deletions() -> None:
    with SessionLocal() as db:
        accounts = account_service.run_due_deletions(db)
        versions = proposal_service.run_due_deletions(db)
    if accounts or versions:
        log.info("Scheduled deletions ran: %s accounts, %s proposal versions", accounts, versions)


async def _deletion_loop() -> None:
    # In the app process, not a separate worker: the demo runs as one backend container. Row locks keep it safe
    # if more processes ever run it.
    while True:
        try:
            await run_in_threadpool(_run_due_deletions)
        except Exception:
            log.exception("Running scheduled deletions failed; trying again next round")
        await asyncio.sleep(DELETION_CHECK_SECONDS)


async def _warm_up_scanner() -> None:
    # In the background, so startup never waits on clamd. It may still be loading signatures, so keep trying.
    stored = Path(settings.upload_dir, "proposals").glob("*.pdf")
    sample = max(stored, key=lambda p: p.stat().st_mtime, default=None)
    for _ in range(SCANNER_WARM_UP_TRIES):
        try:
            await run_in_threadpool(virus_scan.warm_up, sample)
            log.info("Virus scanner is warm")
            return
        except virus_scan.ScannerUnavailable:
            await asyncio.sleep(SCANNER_WARM_UP_RETRY_SECONDS)
    log.warning("Virus scanner never answered at startup; the first upload will warm it")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        auth_service.ensure_admin(db)
    tasks = [asyncio.create_task(_deletion_loop()), asyncio.create_task(_warm_up_scanner())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="ThesisFlow API", lifespan=lifespan)
app.middleware("http")(rate_limit)

def _signed_in(token: str) -> bool:
    # Same session source as the routes, so a dependency override of get_db (tests) applies here too.
    got = app.dependency_overrides.get(get_db, get_db)()
    if not inspect.isgenerator(got):
        return user_for_token(got, token) is not None
    try:
        return user_for_token(next(got), token) is not None
    finally:
        got.close()


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
        # Full check (logout, password change, approval), not just the signature: the DB call runs off the event loop.
        try:
            signed_in = auth.startswith("Bearer ") and await run_in_threadpool(_signed_in, auth[7:])
        except OperationalError as exc:  # exception handlers don't cover middleware
            return await database_unavailable(request, exc)
        if not signed_in:
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
app.include_router(group_controller.router)
app.include_router(meeting_controller.router)


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
    log.info("Database refused a value: %s", exc.orig)
    return JSONResponse(status_code=422, content={"detail": "request: contains a value the server can't store"})


@app.exception_handler(OperationalError)
async def database_unavailable(_: Request, exc: OperationalError):
    # Postgres down or restarting: say so (503) instead of a bare 500, so the UI shows a clear message.
    log.error("Database unavailable: %s", exc.orig)
    return JSONResponse(
        status_code=503,
        content={"detail": "ThesisFlow can't reach its database right now. Try again in a moment."},
        headers={"Retry-After": "5"},
    )
