import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.security import decode_access_token

WINDOW_SECONDS = 60
# Per-IP limits. Behind Docker Desktop every client shows up as one gateway IP, so these are loose;
# guessing one account's password is capped per account instead (LOGIN_PER_ACCOUNT, used by auth_service).
LIMITS = {"/api/auth/login": 60, "/api/auth/register": 30, "/api/": 300}
LOGIN_PER_ACCOUNT = 10
MAX_KEYS = 10_000

# shortcut: in-memory, per-process; move to Redis if we run more than one worker.
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _limit_for(path: str) -> tuple[str, int] | None:
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return prefix, limit
    return None


def hit(key: tuple[str, str], limit: int) -> int | None:
    """Record one request for key. Returns seconds to wait if over the limit, else None."""
    now = time.monotonic()
    if len(_hits) > MAX_KEYS:
        # Callers choose keys (IDs typed at login), so drop idle buckets before the dict grows without bound.
        for k in [k for k, h in _hits.items() if not h or now - h[-1] > WINDOW_SECONDS]:
            del _hits[k]
    hits = _hits[key]
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        return int(WINDOW_SECONDS - (now - hits[0])) + 1
    hits.append(now)
    return None


def too_many(retry: int) -> HTTPException:
    return HTTPException(429, "Too many requests. Try again shortly.", headers={"Retry-After": str(retry)})


async def rate_limit(request: Request, call_next):
    rule = _limit_for(request.url.path)
    if rule is None:
        return await call_next(request)
    prefix, limit = rule
    who = request.client.host if request.client else "unknown"
    if prefix == "/api/":
        # Signed-in users get their own bucket, so users sharing an IP (NAT, Docker Desktop) don't starve each other.
        auth = request.headers.get("authorization", "")
        claims = auth.startswith("Bearer ") and decode_access_token(auth[7:])
        if claims:
            who = f"user:{claims[0]}"
    if retry := hit((who, prefix), limit):
        exc = too_many(retry)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    return await call_next(request)


def reset() -> None:
    _hits.clear()
