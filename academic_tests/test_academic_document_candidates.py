from pathlib import Path
from aihawk.academic_document_candidates import discover

def test_unique_candidates_without_false_verification(tmp_path):
    doc=tmp_path/"Documents"
    doc.mkdir()
    (doc/"Applicant_BSc_Transcripts.pdf").write_bytes(b"verified source candidate")
    (doc/"Applicant_MSc_Transcript.pdf").write_bytes(b"different")
    (doc/"TOEFL_Score.pdf").write_bytes(b"language")
    result=discover(tmp_path,["BSc_transcripts","MSc_transcripts","English_evidence"])
    assert all(r["status"]=="candidate_requires_review" for r in result["roles"].values())
    assert not result["all_documents_verified"]
    assert not result["network_actions"]
    assert all(not f["evidence_verified"] for r in result["roles"].values() for f in r["candidates"])

def test_duplicate_evidence_does_not_create_ambiguity(tmp_path):
    (tmp_path/"Documents").mkdir()
    (tmp_path/"Copies").mkdir()
    (tmp_path/"Documents"/"BSc_Transcript.pdf").write_bytes(b"same content")
    (tmp_path/"Copies"/"BSc_Transcript_duplicate.pdf").write_bytes(b"same content")
    result=discover(tmp_path,["BSc_transcripts"])
    assert result["roles"]["BSc_transcripts"]["status"]=="candidate_requires_review"
    assert len(result["roles"]["BSc_transcripts"]["candidates"])==1

def test_conflicting_candidates_and_ignored_profile(tmp_path):
    (tmp_path/"Documents").mkdir()
    (tmp_path/"Documents"/"MSc_Transcript.pdf").write_bytes(b"a")
    (tmp_path/"Documents"/"MSc_Transcript_other.pdf").write_bytes(b"b")
    private=tmp_path/".aihawk-academic-session"
    private.mkdir()
    (private/"MSc_Transcript.pdf").write_bytes(b"secret")
    result=discover(tmp_path,["MSc_transcripts","reference_1"])
    assert result["roles"]["MSc_transcripts"]["status"]=="ambiguous_candidates"
    assert len(result["roles"]["MSc_transcripts"]["candidates"])==2
    assert result["roles"]["reference_1"]["status"]=="not_found"


def test_unreadable_subfolder_does_not_abort_other_documents(tmp_path,monkeypatch):
    import os
    from pathlib import Path
    from aihawk.academic_document_candidates import discover
    (tmp_path/"no_access").mkdir()
    valid=tmp_path/"valid"
    valid.mkdir()
    (valid/"BSc_Transcript.pdf").write_bytes(b"synthetic-diploma")
    old_scandir=os.scandir
    def inaccessible(directory):
        if Path(directory).name=="no_access":
            raise PermissionError("Synthetic denied directory")
        return old_scandir(directory)
    monkeypatch.setattr(os,"scandir",inaccessible)
    results=discover(tmp_path,["BSc_transcripts"])
    assert results["roles"]["BSc_transcripts"]["status"]=="candidate_requires_review"
    assert len(results["roles"]["BSc_transcripts"]["candidates"])==1
