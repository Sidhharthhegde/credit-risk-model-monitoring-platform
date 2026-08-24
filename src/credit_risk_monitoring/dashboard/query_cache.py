"""Session-local cache for immutable view models used by the presentation layer.

The database revision is part of every key, so a legitimate Phase 12 lifecycle
event invalidates cached current-state projections without touching frozen evidence.
"""

from __future__ import annotations

from typing import Callable, TypeVar

import streamlit as st

from .data_service import DashboardDataService


T = TypeVar("T")


def _remember(service: DashboardDataService, key: tuple[object, ...], loader: Callable[[], T]) -> T:
    stat = service.database_path.stat()
    revision = (stat.st_mtime_ns, stat.st_size)
    cache = st.session_state.setdefault("_control_room_query_cache", {})
    full_key = (revision,) + key
    if full_key not in cache:
        with st.spinner("Opening governed evidence…", show_time=True):
            cache[full_key] = loader()
        # Keep only the current database revision and a small working set.
        stale = [stored for stored in cache if stored[0] != revision]
        for stored in stale:
            cache.pop(stored, None)
        while len(cache) > 12:
            cache.pop(next(iter(cache)))
    return cache[full_key]


def cached_alerts(service: DashboardDataService):
    """Load the alert projection once per database revision and user session."""
    return _remember(service, ("alerts",), service.alerts)


def cached_critical_alerts(service: DashboardDataService):
    """Load frozen critical alert records without opening the full alert ledger."""
    return _remember(service, ("alerts", "CRITICAL"), lambda: service.alerts(severity="CRITICAL"))


def cached_metrics(service: DashboardDataService, *, component: str | None = None):
    """Cache broad metric projections that are otherwise expensive on every rerun."""
    return _remember(service, ("metrics", component), lambda: service.metrics(component=component))
