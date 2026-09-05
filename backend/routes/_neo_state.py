"""Shared state for the NEO routers.

server.py builds all the app-level singletons (mongo db, notify fan-out,
JWT helpers, auth deps, …) and then calls `configure(...)` on this module
BEFORE calling each router's `build_routes()`. The routers read the state
lazily via the exported `state` object.

Keeping a small state carrier here means the router files stay free of
top-level imports from `server.py` (which would be circular).
"""
from __future__ import annotations

from types import SimpleNamespace

# Populated at startup by server.py via configure().
state = SimpleNamespace()


def configure(**kwargs):
    for k, v in kwargs.items():
        setattr(state, k, v)
