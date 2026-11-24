"""Persistent, host-wide access limits. No retry of authentication or write actions."""

from __future__ import annotations
import os
import sqlite3
import time
import math
from pathlib import Path
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from aihawk.academic_browser import PortalPreparationError


def _db_path():
    override = os.environ.get("AIHAWK_PORTAL_LIMIT_DB")
    if override:
        return Path(override)
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "AIHawk"
    base.mkdir(parents=True, exist_ok=True)
    return base / "academic_portal_limits.sqlite3"


class PortalAccessHold(PortalPreparationError):
    pass


class PortalLimits:
    def __init__(self, db=None, clock=time.time):
        self.db = Path(db) if db else _db_path()
        self.clock = clock
        with sqlite3.connect(self.db, timeout=5) as c:
            c.execute("CREATE TABLE IF NOT EXISTS holds(host TEXT PRIMARY KEY, until REAL NOT NULL, status INTEGER NOT NULL)")

    def check(self, hosts):
        with sqlite3.connect(self.db, timeout=5) as c:
            for host in hosts:
                r = c.execute("SELECT until,status FROM holds WHERE host=?", (host.casefold(),)).fetchone()
                if r and (r[0] < 0 or r[0] > self.clock()):
                    msg = "manual review required" if r[0] < 0 else "cooldown " + str(math.ceil(r[0] - self.clock())) + " seconds remaining"
                    raise PortalAccessHold(f"Portal access hold: {host} HTTP {r[1]}; {msg}. No automatic retry.")

    def record(self, host, status, retry_after=None):
        host = host.casefold()
        if status not in (403, 429, 503):
            return
        now = self.clock()
        if status == 403:
            until = -1
        else:
            duration = 3600 if status == 429 else 900
            if retry_after:
                try:
                    delay = float(retry_after)
                except (ValueError, TypeError):
                    try:
                        dt = parsedate_to_datetime(retry_after)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        delay = dt.timestamp() - now
                    except (ValueError, TypeError, OverflowError):
                        delay = 0
                if math.isfinite(delay):
                    duration = max(duration, delay)
            until = now + duration
        with sqlite3.connect(self.db, timeout=5) as c:
            c.execute(
                """INSERT INTO holds VALUES(?,?,?)
            ON CONFLICT(host) DO UPDATE SET
            until=CASE WHEN holds.until<0 OR excluded.until<0 THEN -1 ELSE max(holds.until,excluded.until) END,
            status=CASE WHEN holds.until<0 THEN holds.status ELSE excluded.status END""",
                (host, until, status),
            )

    def clear_reviewed(self, host, *, confirmed=False):
        if confirmed is not True:
            raise PermissionError("Explicit operator review required")
        with sqlite3.connect(self.db, timeout=5) as c:
            r = c.execute("SELECT until FROM holds WHERE host=?", (host.casefold(),)).fetchone()
            if r and r[0] >= 0 and r[0] > self.clock():
                raise PortalAccessHold("Active cooldown cannot be cleared")
            c.execute("DELETE FROM holds WHERE host=?", (host.casefold(),))


def attach_limits(context, hosts, limits=None):
    """Record first-party limits across sessions; never log query strings or credentials."""
    limits = limits or PortalLimits()
    hosts = tuple(h.casefold() for h in hosts)
    limits.check(hosts)

    def matching(host):
        return tuple(h for h in hosts if host == h or host.endswith("." + h))

    def response(r):
        host = (urlsplit(r.url).hostname or "").casefold()
        if r.status in (403, 429, 503):
            for approved in matching(host):
                limits.record(approved, r.status, r.headers.get("retry-after"))

    context.on("response", response)

    def route(r):
        host = (urlsplit(r.request.url).hostname or "").casefold()
        approved = matching(host)
        if approved:
            try:
                limits.check(approved)
            except PortalAccessHold:
                return r.abort()
        r.fallback()

    context.route("**/*", route)
    return limits


def check_access(hosts):
    PortalLimits().check(hosts)
