"""Regression coverage for evidence-based university account status."""

import json
import pytest
from aihawk.academic_account_verification import account_state, require_verified_account
from aihawk.academic_browser import PortalPreparationError


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({}, "not_registered_or_unknown"),
        ({"registration_started": True}, "registration_incomplete"),
        ({"niu_displayed": True}, "provisional_identifier_only"),
        ({"niu_displayed": True, "user_already_exists_notice": True}, "existing_record_unverified"),
        ({"user_already_exists_notice": True, "password_fields_filled": True}, "existing_record_unverified"),
        ({"user_already_exists_notice": True, "login_verified": True}, "existing_account_login_verified"),
        ({"registration_finalized": True, "final_receipt_verified": True, "login_verified": True}, "account_created_and_login_verified"),
        ({"registration_finalized": True, "final_receipt_verified": False, "login_verified": False}, "not_registered_or_unknown"),
    ],
)
def test_account_state(record, expected):
    assert account_state(record) == expected


def test_identity_gate_requires_login_evidence(tmp_path):
    file = tmp_path / "account.json"
    gate = {"identity_gate": {"required": True, "status_file": file.name}}
    record = {"schema_version": "aihawk.academic.account-evidence.v1", "niu_displayed": True, "user_already_exists_notice": True}
    file.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(PortalPreparationError, match="not verified"):
        require_verified_account(gate, manifest_dir=tmp_path)
    record["login_verified"] = True
    file.write_text(json.dumps(record), encoding="utf-8")
    require_verified_account(gate, manifest_dir=tmp_path)


def test_identity_gate_rejects_path_escape(tmp_path):
    for file in ("../leak.json", "C:\\secret.json", "subfolder/file.json"):
        with pytest.raises(PortalPreparationError):
            require_verified_account({"identity_gate": {"required": True, "status_file": file}}, manifest_dir=tmp_path)


def test_ungated_manifest_still_supported(tmp_path):
    require_verified_account({}, manifest_dir=tmp_path)
