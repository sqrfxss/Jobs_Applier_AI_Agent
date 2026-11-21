"""Crash-safe local journal for human-reviewed academic upload batches.

The journal is NOT proof of university receipt. The portal must still show a
file link and Remove control before any file is considered uploaded.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aihawk.academic_browser import PortalPreparationError


class UploadJournal:
    def __init__(self, private_root: Path, fingerprint: str) -> None:
        root = private_root.resolve(strict=True)
        if any((ancestor / ".git").exists() for ancestor in (root, *root.parents)):
            raise PortalPreparationError("Upload status files cannot be stored in a source repository.")
        if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
            raise PortalPreparationError("Invalid reviewed upload fingerprint.")
        self.filename = root / (".aihawk-uploads-" + fingerprint[:16] + ".json")
        self.lock_path = root / ".aihawk-uploads.lock"
        self.fingerprint = fingerprint
        self._locked = False
        self._records: dict[str, dict[str, str]] = {}
        if self.filename.is_symlink() or self.lock_path.is_symlink():
            raise PortalPreparationError("Refusing a redirected upload journal.")
        if self.filename.exists():
            loaded = json.loads(self.filename.read_text(encoding="utf-8"))
            if loaded.get("plan_fingerprint") != fingerprint:
                raise PortalPreparationError("Upload journal does not match the reviewed manifest.")
            records = loaded.get("records")
            if not isinstance(records, dict):
                raise PortalPreparationError("Invalid upload journal records.")
            self._records = records

    def __enter__(self) -> UploadJournal:
        try:
            descriptor = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise PortalPreparationError("Another upload run or stale upload lock exists for this application.") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as out:
            out.write("exclusive academic upload run\n")
        self._locked = True
        return self

    def __exit__(self, *_: Any) -> None:
        if self._locked:
            self.lock_path.unlink(missing_ok=True)
            self._locked = False

    def last_status(self, field: str) -> str | None:
        record = self._records.get(field)
        return record.get("status") if record else None

    def record(self, field: str, status: str) -> None:
        if not self._locked:
            raise PortalPreparationError("Upload checkpoint requires the application's exclusive lock.")
        if status not in {"attempting", "uploaded", "already_uploaded", "unverified"}:
            raise PortalPreparationError("Invalid upload checkpoint state.")
        self._records[field] = {"status": status, "at": datetime.now(UTC).isoformat()}
        snapshot = {
            "schema": "aihawk.academic.upload-checkpoint.v1",
            "plan_fingerprint": self.fingerprint,
            "records": self._records,
        }
        temporary = self.filename.with_suffix(".json.tmp")
        if temporary.is_symlink():
            raise PortalPreparationError("Refusing a redirected temporary upload journal.")
        with temporary.open("w", encoding="utf-8") as out:
            json.dump(snapshot, out, indent=2, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, self.filename)
