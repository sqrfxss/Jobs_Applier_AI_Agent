"""Evidence-based account status, preventing false 'account created' reports.

A provisional identifier, a user-exists message, and an attempted password
are never equivalent to a server-confirmed login. Application preparation
is blocked for manifests that explicitly require a verified university account.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from aihawk.academic_browser import PortalPreparationError


def account_state(evidence: dict[str, Any]) -> str:
    """Make only claims supported by independent portal receipts."""
    if not isinstance(evidence, dict):
        raise PortalPreparationError("Account evidence must be an object.")
    if evidence.get("login_verified") is True:
        if evidence.get("registration_finalized") is True and evidence.get("final_receipt_verified") is True:
            return "account_created_and_login_verified"
        return "existing_account_login_verified"
    if evidence.get("user_already_exists_notice") is True:
        return "existing_record_unverified"
    if evidence.get("niu_displayed") is True:
        return "provisional_identifier_only"
    if evidence.get("registration_started") is True:
        return "registration_incomplete"
    return "not_registered_or_unknown"


def require_verified_account(manifest: dict[str, Any], *, manifest_dir: Path) -> None:
    """Enforce an explicit account gate before opening an authenticated portal.

    For gated manifests, the operator must supply an account state report
    in the same protected directory. No provisional NIU or error screen passes.
    """
    gate = manifest.get("identity_gate")
    if gate is None:
        return
    if (
        not isinstance(gate, dict)
        or set(gate) != {"required", "status_file"}
        or gate["required"] is not True
        or not isinstance(gate["status_file"], str)
        or not gate["status_file"].strip()
    ):
        raise PortalPreparationError("An identity gate requires reviewed account proof.")
    file = Path(gate["status_file"])
    if file.is_absolute() or ".." in file.parts or len(file.parts) != 1:
        raise PortalPreparationError("Identity status file must be directly beside the manifest.")
    path = (manifest_dir / file).resolve()
    if not path.is_file():
        raise PortalPreparationError("Identity verification report is missing.")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != "aihawk.academic.account-evidence.v1":
        raise PortalPreparationError("Identity verification report schema is invalid.")
    state = account_state(record)
    if state not in {"account_created_and_login_verified", "existing_account_login_verified"}:
        raise PortalPreparationError(f"Official university login not verified (state={state}). Do not repeat account creation or submit an application.")
