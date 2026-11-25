"""Evidence-bound classification of supervisor responses, no automatic outgoing email."""

from email.utils import parseaddr
import re


def classify_reply(message, expected_sender, expected_thread):
    if (
        not message.get("id")
        or message.get("thread_id") != expected_thread
        or "SENT" in message.get("labels", [])
        or parseaddr(message.get("from", ""))[1].casefold() != expected_sender.casefold()
    ):
        raise ValueError("Unverified reply identity or thread")
    # Remove quoted previous correspondence and signature separators.
    body = re.split(r"(?mi)^\s*(?:On .+ wrote:|From:|-----Original Message-----|>)", message.get("body", ""), maxsplit=1)[0]
    rules = {
        "auto_reply": r"\b(?:automatic reply|out of office|automated response)\b",
        "declined": r"\b(?:I am not (?:taking|accepting|recruiting)|I cannot supervise|I do not have (?:funding|a position)|no (?:funded )?positions? (?:are )?available)\b",
        "request_documents": r"\b(?:please send|could you send|please provide|could you provide)\b[^.\n]{0,100}\b(?:CV|transcripts?|proposal|documents?)\b",
        "meeting_invitation": r"\b(?:schedule|arrange|set up)\b[^.\n]{0,80}\b(?:meeting|call|interview)\b",
        "encouraged_apply": r"\b(?:encourage you to apply|please apply|welcome to apply)\b",
        "potential_supervision": r"\b(?:I would be willing to supervise|I agree to supervise|I am happy to supervise)\b",
    }
    hits = []
    for label, pattern in rules.items():
        m = re.search(pattern, body, re.I)
        if m:
            hits.append({"classification": label, "excerpt": m.group(0)})
    return {
        "message_id": message["id"],
        "thread_id": expected_thread,
        "status": "review_required",
        "suggested_classifications": hits,
        "formal_supervisor_acceptance": False,
        "email_send_allowed": False,
    }
