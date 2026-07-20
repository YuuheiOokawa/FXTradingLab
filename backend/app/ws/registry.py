"""Tracks currently-connected WebSocket clients across /ws/prices and
/ws/system, for the System page's observability view
(docs/02_SYSTEM_ARCHITECTURE.md "Observability").

In-process only — correct for this app's single-API-process deployment
topology (docs/12_DEPLOYMENT.md: one "api" Railway service). If this app
were ever scaled to multiple API instances, this counter would need to move
to Redis to stay accurate across processes; not this app's shape today, so
kept simple.
"""
from __future__ import annotations

_count = 0


def increment() -> None:
    global _count
    _count += 1


def decrement() -> None:
    global _count
    _count = max(0, _count - 1)


def current_count() -> int:
    return _count
