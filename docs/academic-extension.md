# AIHawk academic workflow — verified development status

Updated 2026-11-21. This fork contains a **standalone university
application preparation workflow**. There is no cross-project integration and
no integration with an external applicant database. The original AIHawk job
application bot is separate and unchanged.

## Implemented functions

| Area | Implementation | Human boundary |
| --- | --- | --- |
| Admission requirements | `academic.py`, `academic_programs.py`, JSON CLIs | The user must review rules against official, current university evidence |
| Source evidence | `academic_sources.py`, `official_fetch.py`, `academic_ops.py capture` | Captures exact text and hash from allowlisted public pages; does not independently interpret legal/admission applicability |
| Document and costs | Exact exam types, legalization, certified translation timing, application fees, deposits, tuition and spouse residence flags | Unknown amounts are not zero; immigration policy needs separate review |
| File preparation | `academic_ops.py`, SHA-256 of actual attachments confined to a private folder | Does not put CV contents in GitHub |
| Review | Escaped, standalone HTML with application values, portal selectors, form/selector fingerprint | User checks the preview and enters an exact approval challenge |
| Form preparation | `academic_browser.py` with optional Playwright | Maps approved text/select/file inputs; never calls submit, click, JavaScript mutation, or model-driven browser tools |
| Read-only portal inspection | `academic_inspect.py` | Extracts candidate labels/selectors without reading entered applicant values |
| Multi-stage form preparation | `academic_stages.py`, `academic_ops.py autofill-stages` | Exact approved host/path and selector mapping for each stage; human navigates between stages and submits manually |
| Network safeguard | All Playwright-routed HTTP requests aborted during the deterministic fill phase | Not a complete browser sandbox: pre-existing WebSockets and side effects of loaded scripts are not guaranteed blocked |
| Final sending | User releases guarded session with a second typed challenge | **Only the user clicks the university's final Submit**; software does not submit |
| Local status | `academic_tracker.py` and `academic_ops.py track-*` | User reports a submission; local proof hash is not proof that the university accepted it |
| Duplicate prevention | Stable private reference per applicant/programme, SQLite state checks | Cannot silently report another submission of a previously submitted record |

Unknown requirements, unsupported fields, ambiguous selectors, unexpected
HTML control types, mismatched readbacks, changed attachments and unapproved
portal domains cause preparation to stop instead of inventing values.
The database records only hashes, domain, timestamps and status, not CVs,
email addresses, browser profiles or receipt contents.

## Verified tests

On the connected Windows computer, the isolated academic modules and tests
passed **89 tests, 1 browser-only test deselected** on the earlier
single-page implementation, and Ruff reported
**All checks passed**. The local Python interpreter was 3.14.

In GitHub Actions, the academic workflow successfully completed:
- Windows, Python 3.11
- Windows, Python 3.12
- Linux, Python 3.11
- Linux, Python 3.12
- Real Chromium exercising a completely intercepted synthetic university
  form. No request to an actual university was made in that browser test.

The full original AIHawk suite and academic CI both passed on the prior
baseline commit `4c503ac3`. Later CI on `e91957d1` passed the stage-planning
checks and synthetic Chromium tests. The final cross-platform CI for the
newest multi-stage commit has been queued and must be checked separately.
The Windows test device is currently offline; no new local test result has
been claimed for the multi-stage code.

See [the prior full successful workflow](https://github.com/sqrfxss/Jobs_Applier_AI_Agent/actions/runs/44723376138)
and [the standalone quickstart](academic-quickstart.md). A separate live
public homepage fetch was performed against
`https://www.maastrichtuniversity.nl/`; it confirmed retrieval and evidence
hashing, **not** any programme-specific eligibility rule.

## Supported local commands

After installing the fork and its optional academic browser dependencies:

```powershell
aihawk-academic capture --url "https://www.maastrichtuniversity.nl/" --host maastrichtuniversity.nl --phrase Maastricht --requirement institution_homepage --out .\homepage-evidence.json
aihawk-academic preview .\application.json .\application-review.html
aihawk-academic inspect .\application.json .\private-field-inventory.json
aihawk-academic autofill .\application.json
aihawk-academic autofill-stages .\multi-stage-application.json
aihawk-academic track-prepared .\application.json
aihawk-academic track-status .\application.json
aihawk-academic track-submitted .\application.json --proof .\receipt.pdf
```

The example domain and phrase are only a source-retrieval smoke test. No real
admissions information is supplied or inferred by these commands; applicants
must obtain actual portal selectors and requirements from the specific
institution. Keep real `application.json`, CVs, SQLite and review files
outside a public repository.

## Not yet production-verified

1. No actual authenticated university portal has been exercised by the new
   form preparer. Per-site controls, sign-in and dynamic workflows still need
   to be inspected and individually tested with permission.
2. Multi-stage forms are supported only where exact paths and reviewed
   selectors have been supplied. Real university multi-step workflows,
   CAPTCHAs and third-party authentication remain unverified.
3. Network request interception is defense in depth, not complete isolation
   from scripts and pre-existing WebSocket connections.
4. The original AIHawk job bot has a broad tool-driven browser and is not
   protected by the separate academic review/approval modules.
5. The complete original AIHawk CI suite on the latest multi-stage branch
   has not yet been verified as successful. A previous full-suite baseline
   was green.
6. University-side receipt or admission decisions cannot be asserted from
   the operator's local status records.

The draft Pull Request must remain unmerged until the remaining original
suite, security review and institution-specific live testing are satisfactory.
