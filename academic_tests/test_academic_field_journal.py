import json
from aihawk.academic_field_journal import record,seed_plan

def test_log_redacts_applicant_data_and_prevents_success_inflation(tmp_path):
    secret="applicant.private@example.invalid"
    row=record(tmp_path,stage="Qualifications",field="#IPQ_ELQUAL_DATE",
               action="fill",status="validation_rejected",
               error_type="PortalPreparationError",
               details="portal rejected date",validation_fields=["Date of test"])
    assert row["server_saved_verified"] is False
    raw=(tmp_path/"Agent_Field_Log.jsonl").read_text(encoding="utf8")
    assert secret not in raw
    assert "Date of test" in raw
    record(tmp_path,stage="Qualifications",field="#IPQ_ELQUAL_DATE",
           action="fill",status="local_verified")
    summary=json.loads((tmp_path/"Agent_Field_Status.json").read_text())
    assert summary["fields"]["Qualifications::#IPQ_ELQUAL_DATE"]["server_saved_verified"] is False
    assert not summary["all_fields_server_verified"]
    record(tmp_path,stage="Qualifications",field="#IPQ_ELQUAL_DATE",
           action="fill",status="server_verified")
    summary=json.loads((tmp_path/"Agent_Field_Status.json").read_text())
    assert summary["fields"]["Qualifications::#IPQ_ELQUAL_DATE"]["server_saved_verified"] is True
    assert summary["all_fields_server_verified"] is True

def test_seeding_is_idempotent_and_never_logs_values(tmp_path):
    plan={"stages":[{"section":"Qualifications",
        "actions":[{"type":"fill","selector":"#IPQ_ELQUAL_DATE","value":"14/Jan/2025"},
                   {"type":"fill","selector":"#PRIVATE","value":"private-birth-date"}]}]}
    assert seed_plan(tmp_path,plan)==2
    one=(tmp_path/"Agent_Field_Log.jsonl").read_text()
    assert "14/Jan/2025" not in one and "private-birth-date" not in one
    assert seed_plan(tmp_path,plan)==2
    assert one==(tmp_path/"Agent_Field_Log.jsonl").read_text()
