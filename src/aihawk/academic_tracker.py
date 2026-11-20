"""Local, redacted history for university applications (no remote sync).

The registry keeps only keyed digests, approved institution hostnames, timestamps
and evidence checksums. "Reported submitted" means the operator said so; it
does not mean the university confirmed acceptance or admission.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_browser import verified_portal_host


class DuplicateApplicationError(PermissionError):
    """A confirmed prior manual submission should not be silently repeated."""


@dataclass(frozen=True)
class ApplicationStatus:
    reference: str
    state: str
    last_updated: str
    institutional_host: str


def application_reference(preview: ApplicationPreview, title: str) -> str:
    """Stable across a change of field values, to catch duplicate attempts."""
    import json

    payload = {
        "applicant": preview.applicant_id,
        "url": preview.opportunity_url.split("?", 1)[0],
        "title": title,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class LocalApplicationRegistry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=10)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                reference TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                institutional_host TEXT NOT NULL,
                state TEXT NOT NULL,
                last_updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL REFERENCES applications(reference),
                action TEXT NOT NULL,
                at TEXT NOT NULL,
                document_sha256 TEXT
            );
            """
        )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> LocalApplicationRegistry:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def state_for(self, reference: str) -> ApplicationStatus | None:
        row = self.db.execute(
            "SELECT reference,state,last_updated,institutional_host FROM applications WHERE reference=?",
            (reference,),
        ).fetchone()
        return ApplicationStatus(*row) if row else None

    def record_prepared(
        self, preview: ApplicationPreview, *, title: str, hosts: tuple[str, ...], now: datetime,
    ) -> ApplicationStatus:
        host = verified_portal_host(preview.opportunity_url, hosts)
        ref = application_reference(preview, title)
        at = _timestamp(now)
        existing = self.state_for(ref)
        if existing is not None and existing.state in ("reported_submitted", "proof_attached"):
            raise DuplicateApplicationError("This programme already has a manually reported submission.")
        with self.db:
            self.db.execute(
                """INSERT INTO applications(reference,fingerprint,institutional_host,state,last_updated)
                VALUES(?,?,?,?,?)
                ON CONFLICT(reference) DO UPDATE SET fingerprint=excluded.fingerprint,
                state=excluded.state,last_updated=excluded.last_updated""",
                (ref, preview.fingerprint(), host, "prepared", at),
            )
            self.db.execute("INSERT INTO events(reference,action,at) VALUES(?,?,?)", (ref, "prepared", at))
        return self.state_for(ref)

    def record_manual_submission(
        self, preview: ApplicationPreview, *, title: str, now: datetime, human_attested: bool,
        proof_path: Path | None = None, private_root: Path | None = None,
    ) -> ApplicationStatus:
        if human_attested is not True:
            raise PermissionError("A direct human attestation is required.")
        ref = application_reference(preview, title)
        existing = self.state_for(ref)
        if existing is None or existing.state != "prepared":
            raise DuplicateApplicationError("No unsubmitted prepared application found for this programme.")
        fingerprint = self.db.execute(
            "SELECT fingerprint FROM applications WHERE reference=?", (ref,),
        ).fetchone()[0]
        if fingerprint != preview.fingerprint():
            raise PermissionError("Application changed after it was prepared. Re-review is required.")
        proof = _private_sha256(proof_path, private_root) if proof_path else None
        state = "proof_attached" if proof else "reported_submitted"
        at = _timestamp(now)
        with self.db:
            updated = self.db.execute(
                """UPDATE applications SET state=?, last_updated=?
                WHERE reference=? AND state='prepared' AND fingerprint=?""",
                (state, at, ref, fingerprint),
            )
            if updated.rowcount != 1:
                raise DuplicateApplicationError("Concurrent or duplicate manual submission prevented.")
            self.db.execute(
                "INSERT INTO events(reference,action,at,document_sha256) VALUES(?,?,?,?)",
                (ref, state, at, proof),
            )
        return self.state_for(ref)

    def audit(self, reference: str) -> tuple[tuple[str, str, str | None], ...]:
        return tuple(self.db.execute(
            "SELECT action,at,document_sha256 FROM events WHERE reference=? ORDER BY id",
            (reference,),
        ).fetchall())


def _timestamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required for audit record.")
    return now.astimezone(UTC).isoformat()


def _private_sha256(path: Path, root: Path | None) -> str:
    if root is None:
        raise ValueError("Private root is required when attaching evidence.")
    target, base = path.resolve(), root.resolve()
    if not target.is_relative_to(base) or not target.is_file() or target.stat().st_size > 20_000_000:
        raise ValueError("Evidence must be a private file within the application directory and under 20 MB.")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(262_144):
            digest.update(chunk)
    return digest.hexdigest()
