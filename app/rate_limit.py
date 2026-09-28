from collections import defaultdict, deque
from time import monotonic

from fastapi import Request
from fastapi.responses import JSONResponse


# This is intentionally process-local. Redis-backed limiting is a later option.
LIMITS: dict[str, tuple[int, int]] = {
    "/auth/signup": (20, 60),
    "/auth/login": (20, 60),
    "/payments/": (30, 60),
    "/payments/webhook/": (60, 60),
}
_requests: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_rate_limit(request: Request) -> tuple[JSONResponse | None, dict[str, str]]:
    rule = LIMITS.get(request.url.path)
    if rule is None:
        return None, {}

    limit, window_seconds = rule
    client_ip = request.client.host if request.client else "unknown"
    key = (client_ip, request.url.path)
    now = monotonic()
    timestamps = _requests[key]
    while timestamps and timestamps[0] <= now - window_seconds:
        timestamps.popleft()

    remaining = max(0, limit - len(timestamps))
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(window_seconds),
    }
    if len(timestamps) >= limit:
        headers["Retry-After"] = str(window_seconds)
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers=headers), headers

    timestamps.append(now)
    headers["X-RateLimit-Remaining"] = str(max(0, limit - len(timestamps)))
    return None, headers

