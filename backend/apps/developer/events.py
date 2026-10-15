"""The catalog of events a webhook can subscribe to.

Only events the platform actually emits appear here — subscribing to one means
you will really receive it. New events are added when (and only when) a real
emit point is wired.
"""
from __future__ import annotations

# event key -> human description. Keep in sync with real dispatch() call sites.
EVENTS = {
    "build.completed": "A project build finished (any outcome).",
}

EVENT_KEYS = list(EVENTS.keys())


def is_known(event: str) -> bool:
    return event in EVENTS
