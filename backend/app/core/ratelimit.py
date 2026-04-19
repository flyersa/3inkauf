"""Shared slowapi Limiter instance.

Kept in its own module so routers can import it without triggering a circular
import with main.py. Apply decorators like ``@limiter.limit("6/minute")`` on
endpoints that accept a ``request: Request`` first parameter.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)
