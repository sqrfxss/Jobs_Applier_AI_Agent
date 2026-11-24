import json
from aihawk.academic_field_journal import record,reconcile_summary,seed_plan

def test_deferred_events_survive_crash_before_summary(tmp_path):
    plan={"stages":[{"section":"Qualifications","actions":[
          {"type":"fill","selector":"#a","value":"private"}]}]}
    assert seed_plan(tmp_path,plan)==1
    record(tmp_path,stage="Qualifications",field="#a",
           action="fill",status="started",defer_summary=True)
    record(tmp_path,stage="Qualifications",field="#a",
           action="fill",status="local_verified",defer_summary=True)
    # This simulates an agent terminated before the per-stage flush.
    old=json.loads((tmp_path/"Agent_Field_Status.json").read_text())
    assert old["fields"]["Qualifications::#a"]["status"]=="planned"
    recovered=reconcile_summary(tmp_path)
    assert recovered["fields"]["Qualifications::#a"]["status"]=="local_verified"
    assert recovered["all_fields_server_verified"] is False
    assert seed_plan(tmp_path,plan)==1
    assert "private" not in (tmp_path/"Agent_Field_Log.jsonl").read_text()

def test_started_does_not_count_as_server_success(tmp_path):
    record(tmp_path,stage="Qualifications",field="#a",action="fill",
           status="started")
    summary=json.loads((tmp_path/"Agent_Field_Status.json").read_text())
    assert not summary["all_fields_server_verified"]

def test_only_explicit_server_readback_counts_as_saved(tmp_path):
    record(tmp_path,stage="Qualifications",field="#a",action="fill",
           status="local_verified",defer_summary=True)
    record(tmp_path,stage="Qualifications",field="#b",action="fill",
           status="server_verified",defer_summary=True)
    summary=reconcile_summary(tmp_path)
    assert not summary["all_fields_server_verified"]
    assert not summary["fields"]["Qualifications::#a"]["server_saved_verified"]
    assert summary["fields"]["Qualifications::#b"]["server_saved_verified"]
