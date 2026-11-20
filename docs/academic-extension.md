# Academic applications extension (development branch)

The fork currently contains **isolated, reviewable building blocks** for academic applications. It does not automatically apply to university portals and does not modify the pre-existing job-application submission engine.

## Implemented

- `aihawk.academic`: evidence-only evaluation of deadlines, exam names, scores and document legalization; missing facts produce `needs_review`.
- `aihawk.academic_sources`: structured records of requirement text, URL, institution and retrieval time; only explicitly allowlisted HTTPS institutional domains are accepted.
- `aihawk.academic_approval`: a one-use approval token bound to a SHA-256 fingerprint of the exact application fields, target URL, applicant identifier and attachment hashes.
- `tests/test_academic.py` and `tests/test_academic_workflow.py`: boundary and regression tests for these components.

## Critical limitations

1. An allowed domain **does not prove** that retrieved information is current, authentic or correctly interpreted. The institutional host must be independently verified and a retrieval component must still fetch and parse official evidence.
2. The approval gate is **not yet wired** into `aihawk.apply` or the browser tool dispatch. Until the browser actions are restricted at code level, a model may potentially submit a form before explicit approval. Do not run real academic submissions with this branch.
3. The existing AIHawk job submission path is unchanged; this release does not implement per-form human approval for that existing path.
4. In-memory approvals are not persisted; only an authenticated, human-operated UI should call `approve`. Never expose approval creation as a model-accessible tool.
5. No live university pages have been fetched or verified by these modules.

## Next engineering changes

- Establish an official-source registry and verified retrieval with dates, documentary evidence, and change detection.
- Add validated, source-specific TOEFL Home Edition rules, fee rules, legalization and certified translation stages, and program-specific requirements.
- Add a browser action monitor and deny any submit actions (including scripts, Enter and navigation-triggered submission) without a one-time approval for the currently filled form. Do not rely on prompting the model.
- Build a human preview/approve UI and an immutable per-application audit trail.
- Create versioned OrbitApply interchange schemas and integration tests.
- Threat-model prompt injection from pages, browser-profile permissions and mailbox access before enabling real submissions.

## Developer checks

Run `pytest -q tests/test_academic.py tests/test_academic_workflow.py`.
No test runs have been verified in this fork yet; GitHub Actions currently reports no workflow runs.
Do not merge this draft PR until CI passes and the browser submission risk is addressed.
