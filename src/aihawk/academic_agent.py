"""Unified private case runner. Prepare what is authorized, report what is blocked.

No final submit, payment, or outgoing correspondence is performed here.
"""

from pathlib import Path
from datetime import datetime, timezone, date
import json
import argparse
import hashlib
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_execution import execute
from aihawk.academic_case_runner import plan
from aihawk.academic_connector_health import status as connector_status


def _private(folder, name, exists=True):
    p = (folder / name).resolve()
    if not p.is_relative_to(folder.resolve()) or (exists and not p.is_file()):
        raise ValueError("Private case file unavailable")
    return p


def writing_jobs(config, folder):
    result = []
    for j in config.get("writing_jobs", []):
        role = j.get("role")
        if role not in ("motivation", "research_proposal") or role not in config.get("required_roles", []):
            continue
        item = {"role": role, "approved_for_upload": False}
        try:
            output = _private(folder, j["output"], exists=False)
            if output.suffix.lower() != ".docx":
                raise ValueError("Expected Word draft")
            brief = _private(folder, j["brief"])
            if hashlib.sha256(brief.read_bytes()).hexdigest() != j["brief_sha256"]:
                raise ValueError("Evidence brief changed")
            if output.exists():
                item["status"] = "existing_draft_review_required"
            else:
                draft = _private(folder, j["reviewed_draft"]) if j.get("reviewed_draft") else None
                if draft and hashlib.sha256(draft.read_bytes()).hexdigest() != j.get("draft_sha256"):
                    raise ValueError("Reviewed draft changed")
                if not draft and j.get("model_api_authorized") is not True:
                    item["status"] = "requires_draft_or_model_authorization"
                    result.append(item)
                    continue
                if role == "research_proposal":
                    from aihawk.academic_research_proposal import deliver

                    deliver(brief, output, reviewed_draft=draft)
                else:
                    from aihawk.academic_motivation import deliver
                    from aihawk.academic_document_gate import require_writing_preflight

                    deliver(brief, output, draft_path=draft)
                    require_writing_preflight(output)
                item["status"] = "draft_generated_review_required"
            item["file"] = output.name
        except Exception as exc:
            item.update(status="blocked", reason=type(exc).__name__)
        result.append(item)
    return result


def actions(blockers):
    out = []
    for item in blockers:
        if item.startswith("document:"):
            role = item.split(":")[1]
            out.append({"action": "resolve_document", "role": role})
        elif item.startswith("degree_eligibility") or item.startswith("course_prerequisites"):
            out.append({"action": "verify_degree_and_course_requirements"})
        elif item.startswith("language_policy"):
            out.append({"action": "verify_official_language_policy"})
        elif item.startswith("credential_policy"):
            out.append({"action": "verify_translation_and_legalization"})
        elif item.startswith("portal_manifest"):
            out.append({"action": "prepare_reviewed_portal_mapping"})
        elif item == "deadline_passed":
            out.append({"action": "archive_or_verify_next_intake"})
        else:
            out.append({"action": "review_blocker", "reason": item})
    return out


def run(folder, *, run_draft=False):
    folder = folder.resolve(strict=True)
    if any((p / ".git").exists() for p in (folder, *folder.parents)):
        raise ValueError("Private application data must not live in Git")
    result = {
        "schema": "aihawk.agent.case.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "final_submission": False,
        "user_approval_required": True,
        "email_sent": False,
        "connector_configuration": connector_status(),
    }
    from aihawk.academic_chatgpt_bridge import request_sync

    case = folder / "Execution_Case.json"
    state = folder / "AIHawk_Workflow_State.json"
    if not case.exists() and not state.exists():
        raise ValueError("No case files found")
    if state.exists():
        data = json.loads(state.read_text(encoding="utf8"))
        result["chatgpt_sync"] = request_sync(folder, data)
        snap = folder / "Gmail_Thread_Latest.json"
        thread = json.loads(snap.read_text(encoding="utf8")) if snap.exists() else None
        result["outreach"] = plan(data, today=date.today(), thread=thread)
        if data.get("application_submitted") is True or data.get("status") in ("Submitted", "Closed", "Rejected", "Admitted"):
            result["status"] = "terminal"
            atomic_json(folder / "Agent_Report.json", result)
            return result
    if case.exists():
        config = json.loads(case.read_text(encoding="utf8"))
        from aihawk.academic_document_candidates import discover

        result["document_candidates"] = discover(folder, config.get("required_roles", []), config.get("documents", {}))
        if not state.exists():
            result["chatgpt_sync"] = request_sync(folder, config)
        result["writing"] = writing_jobs(config, folder) if run_draft else []
        report = execute(case, run_draft=run_draft)
        result["preflight"] = report
        result["next_actions"] = actions(report["blockers"])
        result["status"] = report["result"]
    else:
        result["status"] = "outreach_or_admissions_review"
        result["next_actions"] = [{"action": x} for x in result.get("outreach", {}).get("tasks", [])]
    atomic_json(folder / "Agent_Report.json", result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--run-draft", action="store_true")
    a = p.parse_args()
    r = run(a.folder, run_draft=a.run_draft)
    print(
        json.dumps(
            {"status": r["status"], "actions": r.get("next_actions", []), "final_submission": False, "report": str(a.folder / "Agent_Report.json")},
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
