"""Shared slowapi Limiter instance.

Kept in its own module so routers can import it without triggering a circular
import with main.py. Apply decorators like ``@limiter.limit("6/minute")`` on
endpoints that accept a ``request: Request`` first parameter.

Rate-limit bucket key: the **real client IP**, extracted in this order:

1. Leftmost entry of ``X-Forwarded-For`` when the header is present. The
   deployment contract is that the **immediate upstream proxy OVERWRITES**
   this header (our bundled ``nginx.conf`` sets it to ``$remote_addr``,
   not ``$proxy_add_x_forwarded_for``), so a client-supplied XFF cannot
   poison the bucket.
2. ``request.client.host`` — the direct socket peer. Used when the app is
   deployed without any proxy in front.

This fixes the pentest-reported "one global bucket" collapse where the
default ``slowapi.util.get_remote_address`` returned the nginx container IP
for every request and a single attacker could DoS login / register for the
whole application from one socket.
"""
from fastapi import Request
from slowapi import Limiter


def _client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "anon"


limiter = Limiter(key_func=_client_key)
