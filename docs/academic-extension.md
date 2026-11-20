# Academic applications extension — development branch

## Verified implementation status (2026-11-20)

This extension is a **working, tested offline academic eligibility and review foundation**, not a completed university portal autopilot. It does not send applications and does not alter AIHawk's existing job-submission code.

### Modules

| Module | Function | Verification |
| --- | --- | --- |
| `aihawk.academic` | Deterministic eligibility for deadline, accepted exam, score and legalization | Automated unit tests |
| `aihawk.academic_sources` | Evidence metadata with HTTPS allowlist, timestamps and text | Automated unit tests; no live source verification |
| `aihawk.academic_approval` | One-use fingerprint-bound approval record | Automated unit tests |
| `aihawk.academic_review` | Draft/review/approval/manual-submission state machine and redacted audit | Automated unit tests |
| `aihawk.academic_cli` | JSON input -> JSON eligibility report; never submits | Automated unit tests |

### Locally verified checks

On a connected Windows host, 22 tests across:
- `tests/test_academic.py`
- `tests/test_academic_workflow.py`
- `tests/test_academic_cli.py`
- `tests/test_academic_review.py`

completed successfully with `22 passed` using `py -m pytest`. This was a **module-level** test run from downloaded GitHub files, not the complete original repository test suite. The fork currently has no GitHub Actions runs, so CI remains unverified.

### Run offline evaluation

1. Install Python 3.11 or 3.12 and the original project's developer dependencies, or provide the `src` directory on `PYTHONPATH`.
2. Prepare a UTF-8 JSON document with this structure:

```json
{
  "applicant": {
    "language_test": "TOEFL Home Edition",
    "language_score": 95,
    "documents_legalized": false
  },
  "opportunities": [
    {
      "institution": "Example University (illustrative only)",
      "program": "MSc Example",
      "official_hosts": ["example.edu"],
      "requirements": {
        "deadline": "2027-02-01",
        "accepted_language_tests": ["TOEFL Home Edition"],
        "minimum_language_score": 90,
        "requires_legalization_at_application": false
      },
      "sources": []
    }
  ]
}
```

The illustrative entry **does not constitute a verified real programme**. Because `sources` is empty, the result is `needs_review`.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
py -m aihawk.academic_cli evaluate .\academic-input.json .\academic-output.json --date 2026-11-20
py -m pytest -q tests/test_academic.py tests/test_academic_workflow.py tests/test_academic_cli.py tests/test_academic_review.py
```

### Safety restrictions

- All academic CLI reports explicitly set `submission_enabled=false`.
- Allowed source URLs only validate domain allowlisting and timestamp metadata; **they do not independently authenticate the contents of an official page**.
- Academic approval and review code is *not* connected to the main browser executor. Never treat these modules as protection for the original AIHawk browser flow.
- No AI model receives permission to approve an application.
- Audit exports exclude applicant names, form values and credentials, keeping a fingerprint and event timestamps.
- No real university form was opened or submitted as part of these tests.

### Outstanding before a production-ready system

1. Implement authenticated academic source retrieval and manual/automated cross-checks of the actual university requirements.
2. Implement institutional portal adapters that only perform reviewed operations and cannot bypass a browser-level no-submit policy; validate keyboard, JavaScript and navigation submission vectors.
3. Build a real human preview/approval UI wired to a server-side, durable, one-use authorization check.
4. Add provenance-linked credential/fees/visa/legalization schemas and source versioning.
5. Add versioned OrbitApply import/export and end-to-end tests.
6. Validate under supported Python 3.11/3.12 versions and run the original repository's full test suite and CI before merging.

Do not merge this draft PR or enable automatic university submission until the remaining gates have been implemented and verified.
