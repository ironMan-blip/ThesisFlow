import json
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis import Redis
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.security import decode_access_token

WINDOW_SECONDS = 60
# Per-IP limits. Behind Docker Desktop every client shows up as one gateway IP, so these are loose;
# guessing one account's password is capped per account instead (used by auth_service, failed logins only).
LIMITS = {"/api/auth/login": 60, "/api/auth/register": 30, "/api/": 300}
# Per account and IP, so someone guessing from one IP can't lock the owner out from another.
LOGIN_PER_ACCOUNT = 10
# Per account across all IPs: caps guessing spread over many IPs. IPs the account logged in from before skip it,
# so a guesser spread over many IPs can't lock the owner out of their usual devices.
LOGIN_PER_ACCOUNT_ALL_IPS = 100
KNOWN_IPS_PER_ACCOUNT = 5

# Shared by every backend process, so limits hold across workers and restarts. Buckets expire on their own.
redis = Redis.from_url(settings.redis_url, decode_responses=True)

# Sliding window in one atomic step, timed by the Redis clock so every worker agrees.
# Returns seconds to wait if over the limit, else 0.
_HIT = """
local key, limit, window = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', key, '-inf', '(' .. (now - window))
if redis.call('ZCARD', key) >= limit then
  local oldest = tonumber(redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2])
  return math.floor(window - (now - oldest)) + 1
end
redis.call('ZADD', key, now, ARGV[3])
redis.call('EXPIRE', key, window + 1)
return 0
"""
_hit_script = redis.register_script(_HIT)


def _key(*parts: object) -> str:
    # JSON keeps parts apart: an ID typed as "x|1.2.3.4" can't land in the bucket for ("x", "1.2.3.4").
    return "rl:" + json.dumps(parts)


def is_known_ip(account: str, ip: str) -> bool:
    return ip in redis.lrange(_key("ips", account), 0, -1)


def remember_ip(account: str, ip: str) -> None:
    # Most recent first; the oldest drops off past KNOWN_IPS_PER_ACCOUNT. Keyed only by accounts that logged in.
    key = _key("ips", account)
    with redis.pipeline() as pipe:
        pipe.lrem(key, 0, ip).lpush(key, ip).ltrim(key, 0, KNOWN_IPS_PER_ACCOUNT - 1).execute()


def _limit_for(path: str) -> tuple[str, int] | None:
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return prefix, limit
    return None


def hit(key: tuple[str, ...], limit: int) -> int | None:
    """Record one request for key. Returns seconds to wait if over the limit, else None."""
    retry = _hit_script(keys=[_key(*key)], args=[limit, WINDOW_SECONDS, uuid.uuid4().hex], client=redis)
    return retry or None


def unhit(key: tuple[str, ...]) -> None:
    """Take back the last request recorded for key (e.g. a login that turned out to be right)."""
    redis.zpopmax(_key(*key))


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
    # The Redis client is blocking; keep it off the event loop.
    if retry := await run_in_threadpool(hit, (who, prefix), limit):
        exc = too_many(retry)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    return await call_next(request)


def reset() -> None:
    """Tests only: wipes the whole Redis database the client points at."""
    redis.flushdb()
