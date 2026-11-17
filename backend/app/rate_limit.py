import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis import Redis, RedisError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.security import DEVICE_COOKIE, decode_access_token, device_account

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
# While Redis is down, wait this long before trying it again, so each request doesn't wait on a dead server.
REDIS_RETRY_SECONDS = 10
# Fallback store only: callers choose keys (IDs typed at login), so its size is capped.
MAX_KEYS = 10_000

# Shared by every backend process, so limits hold across workers and restarts. Buckets expire on their own.
# Short timeouts: a hung Redis must not hang logins.
redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5)
log = logging.getLogger(__name__)
T = TypeVar("T")
_redis_down_until = 0.0

# Every request is also counted in this process's memory. Redis adds the count across processes; if it fails,
# memory alone keeps limiting, with the counts from before the outage. After the outage memory still holds what
# Redis missed, so a request must pass both.
_hits: dict[str, deque[float]] = defaultdict(deque)
_next_sweep = 0.0
_known_ips: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=KNOWN_IPS_PER_ACCOUNT))


def _try_redis(call: Callable[[], T], default: T) -> T:
    """Run call against Redis; give default instead while Redis is down."""
    global _redis_down_until
    if time.monotonic() >= _redis_down_until:
        try:
            result = call()
        except RedisError as exc:
            if _redis_down_until == 0.0:
                log.warning("Redis unavailable, rate limits use memory only: %s", exc)
            _redis_down_until = time.monotonic() + REDIS_RETRY_SECONDS
            return default
        if _redis_down_until:
            log.warning("Redis is back, rate limits use it again")
            _redis_down_until = 0.0
        return result
    return default


def _memory_hit(key: str, limit: int) -> int | None:
    global _next_sweep
    now = time.monotonic()
    if len(_hits) > MAX_KEYS and now >= _next_sweep:
        # At most one full scan a second, so a flood of live keys can't make every request scan them all.
        _next_sweep = now + 1
        for k in [k for k, h in _hits.items() if not h or now - h[-1] > WINDOW_SECONDS]:
            del _hits[k]
    hits = _hits[key]
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        return int(WINDOW_SECONDS - (now - hits[0])) + 1
    hits.append(now)
    return None


def _memory_remember_ip(key: str, ip: str) -> None:
    if ip not in _known_ips[key]:
        _known_ips[key].append(ip)

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
    key = _key("ips", account)
    if ip in _known_ips.get(key, ()):
        return True
    if _try_redis(lambda: ip in redis.lrange(key, 0, -1), False):
        _memory_remember_ip(key, ip)  # so this process still knows it if Redis goes down
        return True
    return False


def remember_ip(account: str, ip: str) -> None:
    # Most recent first; the oldest drops off past KNOWN_IPS_PER_ACCOUNT. Keyed only by accounts that logged in.
    key = _key("ips", account)

    def use_redis() -> None:
        with redis.pipeline() as pipe:
            pipe.lrem(key, 0, ip).lpush(key, ip).ltrim(key, 0, KNOWN_IPS_PER_ACCOUNT - 1).execute()

    _memory_remember_ip(key, ip)
    _try_redis(use_redis, None)


def _limit_for(path: str) -> tuple[str, int] | None:
    for prefix, limit in LIMITS.items():
        if path.startswith(prefix):
            return prefix, limit
    return None


def hit(key: tuple[str, ...], limit: int) -> int | None:
    """Record one request for key. Returns seconds to wait if over the limit, else None."""
    k = _key(*key)

    def use_redis() -> int | None:
        return _hit_script(keys=[k], args=[limit, WINDOW_SECONDS, uuid.uuid4().hex], client=redis) or None

    if retry := _memory_hit(k, limit):
        return retry
    if (retry := _try_redis(use_redis, None)) and _hits.get(k):
        _hits[k].pop()  # refused, so it doesn't count in memory either
    return retry


def unhit(key: tuple[str, ...]) -> None:
    """Take back the last request recorded for key (e.g. a login that turned out to be right)."""
    k = _key(*key)
    if _hits.get(k):
        _hits[k].pop()
    _try_redis(lambda: redis.zpopmax(k), None)


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
    elif prefix == "/api/auth/login" and (account := device_account(request.cookies.get(DEVICE_COOKIE))):
        # Same idea for logins: a guesser sharing the IP can't use up the owner's browser's budget.
        # Keyed by account, not cookie, so logging in again for fresh cookies gives no extra buckets.
        who = f"device:{account}"
    # The Redis client is blocking; keep it off the event loop.
    if retry := await run_in_threadpool(hit, (who, prefix), limit):
        exc = too_many(retry)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    return await call_next(request)


def reset() -> None:
    """Tests only: wipes the whole Redis database the client points at, and the memory fallback."""
    global _redis_down_until, _next_sweep
    _hits.clear()
    _known_ips.clear()
    _redis_down_until = _next_sweep = 0.0
    redis.flushdb()
