# Academic applications extension (development branch)

This fork is being extended toward a reviewed, auditable university-application workflow. Existing job-search and submission code remains unchanged in this initial patch.

## Implemented foundation

- `aihawk.academic` provides a deterministic, explicit-data-only eligibility check.
- Three outcomes: `eligible`, `ineligible`, and `needs_review`.
- Checks deadlines, language test name and score, and document legalization at application.
- Missing deadlines or requirements trigger human review rather than an invented approval.
- The evaluation uses an injected date for reproducible tests.
- The module does **not** integrate with search, browser automation or the application submission flow yet.

## Safety and implementation priorities

1. Prevent submission by browser tools until the user approves the exact filled application.
2. Verify facts from official university pages; keep source URL, retrieval timestamp, and requirement provenance.
3. Preserve source-specific language exam types (e.g. TOEFL Home Edition vs. test-center TOEFL), score scales, and per-program rules.
4. Model translations, authentication/legalization stages, fees, scholarships, and spouse-related constraints separately.
5. Add academic-opportunity discovery and OrbitApply exchange through a versioned, documented interface.
6. Keep CVs, passwords, browser profiles, and API credentials out of Git; avoid sending private data to third parties without disclosure and consent.

## Developer check

Run `pytest -q tests/test_academic.py`. This initial module has no network or browser dependencies.
Do not merge into `main` until CI tests pass and the submit path receives a code-level approval gate.
