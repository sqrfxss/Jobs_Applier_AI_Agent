# Academic extension status — independent of OrbitApply

Updated 2026-11-20. This branch implements a standalone **evidence-capture,
preliminary-eligibility and human-review workflow**, not a production
automatic submission bot. No connection, deployment or database write to
OrbitApply has been made.

## What is implemented

| Component | Location | Result |
| --- | --- | --- |
| Preliminary programme checks | `academic.py`, `academic_cli.py` | Deadline, test type, score and legalization |
| Detailed admissions checks | `academic_programs.py`, `academic_program_cli.py` | Exact TOEFL format, translations, document timing, fees, deposits, tuition and family-visa review flags |
| Source metadata checks | `academic_sources.py` | HTTPS hostname allowlist, timestamps and quote metadata |
| Official public page capture | `official_fetch.py`, `academic_ops.py capture` | Bounded public HTML, text and PDF; exact phrase excerpt, timestamp and SHA-256 |
| Application preview | `academic_portal.py`, `academic_ops.py preview` | Static HTML with escaped values and no form submit |
| Manual browser handoff | `academic_ops.py handoff` | Explicit terminal fingerprint challenge, official host allowlist |
| Review & approvals | `academic_approval.py`, `academic_review.py` | One-use fingerprint-bound approval, edit invalidation and redacted audit |
| Experimental data exchange | `orbitapply_bridge.py` | A dormant offline schema only; not integrated or invoked |

Unknown costs, missing language/translation or legalization requirements and
unconfirmed immigration rules are **not** assumed to be favourable. Source
metadata alone cannot establish the truth of admission conditions; `academic_cli`
never returns final confirmed eligibility from self-reported quotes.

## Verified tests

**59 targeted Python tests passed**, with `ruff check` reporting **all checks
passed** on the connected Windows system, in the isolated test directory
`F:\AIHawk_test`. The tested Python there is 3.14; the separate GitHub workflow
runs supported Python 3.11 and 3.12 on Linux and Windows and has reported
successful executions.

One live public-source test captured the homepage of
`https://www.maastrichtuniversity.nl/` with an exact phrase and a document
hash. It did **not** verify any specific admissions requirement.

The original AIHawk test suite includes expensive browser/integration tests.
Its full CI green status on the final branch has not yet been confirmed;
independent academic test success is not proof that all upstream tests pass.

## How to run

See [academic-quickstart.md](academic-quickstart.md) for the local JSON manifest
and commands. From a Python environment containing this branch:

```powershell
py -m aihawk.academic_ops capture --url "https://www.maastrichtuniversity.nl/" --host "maastrichtuniversity.nl" --phrase Maastricht --requirement institution_homepage --out .\homepage-evidence.json
py -m aihawk.academic_ops preview .\application.json .\application-review.html
py -m aihawk.academic_ops handoff .\application.json
py -m aihawk.academic_program_cli .\programme.json .\programme-review.json --date 2026-11-20
```

The homepage example is only a fetch test. Do not enter real applicant
information into a public GitHub checkout. Keep `application.json`,
attachments and review HTML in a private, Git-ignored folder.

## Remaining prerequisites for automatic academic submission

1. Production institutional adapters: every portal has distinct forms,
   authentication, uploads, consent screens, closing dates and confirmation
   mechanisms.
2. Browser-enforced prevention of early/unreviewed submissions. The original
   AIHawk model has broad browser access, including actions that may submit
   forms before the final submit call. A prompt or in-memory approval record
   alone does not solve this.
3. Authenticated, persistent human approval at the exact submission boundary,
   rather than only a manually reviewed preview.
4. Site-specific end-to-end tests against authorized test accounts and test
   pages, including duplicate prevention and submission-proof checks.
5. Production hardening: privacy, consent, third-party model disclosures,
   dependency audit, prompt-injection resistance and supported-platform CI.

**Do not merge as production-ready or use for automatic university submissions.**
`main` remains unchanged; the academic implementation is in `develop`
and its draft pull request.
