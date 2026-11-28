"""In-memory per-IP sliding-window rate limiter."""
import threading
import time
from collections import defaultdict, deque

LIMIT = 30
WINDOW = 60  # requests per IP per minute

_hits: dict[str, deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()


def _prune_expired(now: float, current_ip: str) -> None:
    """Drop IP entries whose newest timestamp is older than WINDOW."""
    stale = [k for k, v in _hits.items() if k != current_ip and (not v or now - v[-1] > WINDOW)]
    for key in stale:
        del _hits[key]


def is_rate_limited(ip: str) -> bool:
    """Return True when ip has reached LIMIT requests inside the sliding WINDOW."""
    now = time.time()
    with _hits_lock:
        _prune_expired(now, ip)
        q = _hits[ip]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= LIMIT:
            return True
        q.append(now)
        return False
