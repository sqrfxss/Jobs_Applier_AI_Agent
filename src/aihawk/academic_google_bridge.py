"""Optional local Google OAuth. User performs one-time consent in official browser.
Read-only Gmail plus Sheets access; never send email or change account settings.
"""

import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ("https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/spreadsheets")


def _private_path(env, *, must_exist=False):
    value = os.environ.get(env)
    if not value:
        raise RuntimeError(env + " is not configured")
    p = Path(value).resolve()
    if any((d / ".git").exists() for d in p.parents):
        raise ValueError("OAuth files must be outside Git")
    if must_exist and not p.is_file():
        raise FileNotFoundError(env + " file unavailable")
    return p


def _save(path, creds):
    path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=".oauth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            f.write(creds.to_json())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def consent():
    """Run only after operator deliberately invokes setup; never on ordinary execution."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client = _private_path("AIHAWK_GOOGLE_CLIENT_FILE", must_exist=True)
    token = _private_path("AIHAWK_GOOGLE_TOKEN_FILE")
    if token.exists():
        raise FileExistsError("Existing token; use health check, not duplicate consent")
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        authorization_prompt_message="Authorize read-only Gmail and Sheets in the official Google browser.",
        success_message="Authorization complete. Return to AIHawk.",
    )
    _save(token, creds)


def services():
    token = _private_path("AIHAWK_GOOGLE_TOKEN_FILE", must_exist=True)
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.has_scopes(SCOPES):
        raise RuntimeError("Required scopes not granted")
    if not creds.valid:
        if not creds.refresh_token:
            raise RuntimeError("OAuth consent required")
        creds.refresh(Request())
        _save(token, creds)
    return build("gmail", "v1", credentials=creds, cache_discovery=False), build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_thread(thread_id):
    if not thread_id or not thread_id.isalnum():
        raise ValueError("Exact Gmail thread ID required")
    gmail, _ = services()
    return gmail.users().threads().get(userId="me", id=thread_id, format="full").execute(num_retries=0)


def patch_unique_existing_row(sheets, *, spreadsheet_id, sheet_name, id_column, record_id, updates):
    """Only updates an existing unique ID. No automatic append or credential columns."""
    import re

    if not re.fullmatch(r"[A-Z]{1,2}", id_column) or not record_id:
        raise ValueError("Invalid key")
    if not updates or any(not re.fullmatch(r"[A-Z]{1,2}", c) or c in ("S", "T", id_column) for c in updates):
        raise ValueError("Unsafe update columns")
    tab = "'" + sheet_name.replace("'", "''") + "'"
    api = sheets.spreadsheets().values()
    rows = api.get(spreadsheetId=spreadsheet_id, range=tab + "!" + id_column + ":" + id_column).execute(num_retries=0).get("values", [])
    matches = [i + 1 for i, r in enumerate(rows) if r and str(r[0]) == record_id]
    if len(matches) != 1 or matches[0] < 2:
        raise ValueError("Existing row not unique")
    row = matches[0]

    def read(c):
        return api.get(spreadsheetId=spreadsheet_id, range=f"{tab}!{c}{row}").execute(num_retries=0).get("values", [])

    if read(id_column) != [[record_id]]:
        raise RuntimeError("Row moved; stop")
    body = {"valueInputOption": "RAW", "data": [{"range": f"{tab}!{col}{row}", "values": [[value]]} for col, value in updates.items()]}
    api.batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute(num_retries=0)
    if read(id_column) != [[record_id]] or any(read(c) != [[v]] for c, v in updates.items()):
        raise RuntimeError("Tracker readback mismatch")
    return {"row": row, "readback_verified": True}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("consent", "health"))
    a = p.parse_args()
    if a.action == "consent":
        consent()
    else:
        g, s = services()
        # Verify actual authorized API call; avoid exposing email address or labels.
        g.users().getProfile(userId="me").execute(num_retries=0)
        print(json.dumps({"gmail_live": True, "sheets_library_ready": True, "sheets_live_verified": False}))
