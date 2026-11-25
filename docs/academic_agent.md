# Academic application agent (experimental)

The `aihawk.academic_*` modules add evidence-reviewed academic opportunity discovery, eligibility checks, personalized motivation-letter drafting, and draft-only university form automation. They are separate from the original job-application pipeline.

## Setup

Install with Python 3.11 or 3.12:

```bash
python -m pip install -e '.[academic]'
python -m playwright install chrome
```

For testing:

```bash
python -m pip install pytest
python -m pytest -q academic_tests
```

On Windows the optional launcher `scripts/run_academic.ps1` resolves the repository's `src` directory automatically. For example:

```powershell
.\scripts\run_academic.ps1 -Mode AgentCase -CaseFolder "D:\private-applications\example"
```

Keep all application documents, transcripts, IDs, reference details, CVs, university credentials, and case JSON files outside the Git repository. The public repository includes **code and synthetic tests only**. A private case folder may contain `Execution_Case.json` and approved application manifests.

## Safe operating contract

- Discovery and eligibility classification are evidence-dependent; a filename is not proof that a document is correct.
- Document candidates are listed with SHA-256 hashes and remain unverified until matched to reviewed evidence.
- Field journal events distinguish planned, locally entered, and freshly server-verified values. A Save click is not a receipt.
- The journal is append-only. Stage summaries can be reconstructed after an interruption; case data never enter this repository.
- Document uploads are idempotent where university receipts permit safe verification.
- Login, OTP, CAPTCHA and institution-specific blocks must be completed through authorized procedures. Do not circumvent challenges.
- The academic runner never clicks the final Submit button, sends messages, makes payments or asserts a submitted application without independently verified evidence.
- The Google/Gmail bridge is a connector handoff. The local process needs configured integrations for independent online operations; test doubles are not live verification.
- Automated letters require a configured model integration and checked CV/programme evidence, plus human review before use.

## Testing and performance

Academic tests live in `academic_tests/` to avoid inheriting fixtures from the upstream product's `tests/conftest.py`. The GitHub Actions workflow template is in docs/ci/academic-agent-qa.yml. It is not active until a maintainer with GitHub workflow permission moves it into .github/workflows/.

Synthetic performance baselines (Windows machine; not a university latency guarantee):

| Operation | Before | After |
|---|---:|---:|
| Initial journal seeding for 65 fields, median | 876 ms | 3 ms |
| Filling 65 mocked browser fields with journal | 5.10 s | 4.03 s |

Live university portals have variable server response times and may block or invalidate data. Real application completion must be separately confirmed.

## Architecture

`academic_agent.py`: case orchestration and preflight; `academic_document_candidates.py`: bounded read-only candidate discovery; `academic_session_batch.py`: staged draft filling and independent readback; `academic_field_journal.py`: crash-tolerant event history; `academic_session_supervisor.py`: recovery and login classification; `academic_motivation_auto.py`: grounded document drafting with model configuration.

This is an experimental extension, not a guarantee of bug-free or fully autonomous submissions.
