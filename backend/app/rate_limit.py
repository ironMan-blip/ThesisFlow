import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

WINDOW_SECONDS = 60
# Auth endpoints get a tight limit to stop password guessing and sign-up spam.
LIMITS = {"/api/auth/login": 10, "/api/auth/register": 10, "/api/": 300}

# shortcut: in-memory, per-process; move to Redis if we run more than one worker.
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _limit_for(path: str) -> tuple[str, int] | None:
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return prefix, limit
    return None


async def rate_limit(request: Request, call_next):
    rule = _limit_for(request.url.path)
    if rule is None:
        return await call_next(request)
    prefix, limit = rule
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _hits[(ip, prefix)]
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        retry = int(WINDOW_SECONDS - (now - hits[0])) + 1
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Try again shortly."},
            headers={"Retry-After": str(retry)},
        )
    hits.append(now)
    return await call_next(request)


def reset() -> None:
    _hits.clear()
