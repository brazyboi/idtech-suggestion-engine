"""
Shared slowapi Limiter instance — see ARCHITECTURE.md D3.

Lives in its own module so both main.py (which registers it on the app)
and routers/chat.py (which decorates endpoints with it) can import it
without a circular import.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
