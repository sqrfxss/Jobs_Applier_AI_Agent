import pytest
from aihawk.academic_reply_review import classify_reply


def message(body):
    return {"id": "a1", "thread_id": "t1", "from": "Professor <faculty@example.edu>", "labels": ["INBOX"], "body": body}


def test_reply_semantic_review_only():
    r = classify_reply(message("Please send your CV.\nI would be willing to supervise."), "faculty@example.edu", "t1")
    assert {h["classification"] for h in r["suggested_classifications"]} == {"request_documents", "potential_supervision"}
    assert r["formal_supervisor_acceptance"] is False and r["email_send_allowed"] is False


def test_reply_wrong_identity():
    with pytest.raises(ValueError):
        classify_reply(message("Please apply"), "other@example.edu", "t1")


def test_quoted_previous_message_not_classified():
    r = classify_reply(message("Thank you.\nOn Friday applicant wrote:\nPlease send CV."), "faculty@example.edu", "t1")
    assert r["suggested_classifications"] == []
