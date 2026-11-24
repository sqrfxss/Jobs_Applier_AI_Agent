"""Durable budgets for explicit portal actions, not arbitrary asset traffic.

The reservation is made before the action and is not refunded on timeout:
the server may already have processed it. Shared across browser processes.
"""
from __future__ import annotations
import sqlite3,time
from urllib.parse import urlsplit
from aihawk.academic_portal_limits import PortalLimits,PortalAccessHold

POLICIES={"auth_request":(1,1800),"auth_verify":(1,600),"portal_entry":(3,300),"draft_save":(6,60),"upload":(12,60)}
class ActionBudget:
    def __init__(self,db=None,clock=time.time):
        self.limits=PortalLimits(db,clock=clock)
        self.clock=clock
        self.db=self.limits.db
        with sqlite3.connect(self.db,timeout=5) as c:
            c.execute("CREATE TABLE IF NOT EXISTS actions(host TEXT, kind TEXT, at REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS actions_lookup ON actions(host,kind,at)")
    def reserve(self,host,kind):
        host=host.casefold().strip()
        if not host or any(c in host for c in "/:?@"):raise ValueError("Invalid host")
        if kind not in POLICIES:raise ValueError("Unknown action category")
        limit,window=POLICIES[kind];now=self.clock()
        with sqlite3.connect(self.db,timeout=5) as c:
            c.execute("BEGIN IMMEDIATE")
            hold=c.execute("SELECT until,status FROM holds WHERE host=?",(host,)).fetchone()
            if hold and (hold[0]<0 or hold[0]>now):
                raise PortalAccessHold(f"Portal access hold: {host} HTTP {hold[1]}")
            c.execute("DELETE FROM actions WHERE at<?",(now-max(w for _,w in POLICIES.values()),))
            rows=c.execute("SELECT at FROM actions WHERE host=? AND kind=? AND at>? ORDER BY at",(host,kind,now-window)).fetchall()
            if len(rows)>=limit:
                raise PortalAccessHold(f"Action budget exhausted: {host} {kind}; next eligible after {max(0,round(rows[0][0]+window-now))} seconds. No automatic retry.")
            c.execute("INSERT INTO actions VALUES(?,?,?)",(host,kind,now))
    def reserve_url(self,url,kind,official_hosts):
        host=(urlsplit(url).hostname or "").casefold()
        approved=[h.casefold() for h in official_hosts if host==h.casefold() or host.endswith("."+h.casefold())]
        if not approved or urlsplit(url).scheme!="https":raise ValueError("Unapproved portal")
        # Broadest approved parent prevents subdomain switching from avoiding budget.
        self.reserve(min(approved,key=len),kind)
