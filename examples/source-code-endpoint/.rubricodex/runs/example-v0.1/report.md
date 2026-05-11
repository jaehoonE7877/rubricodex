# Rubricodex Report

## Summary
- Decision: pass_with_warnings
- Scoring model: counts-v0.1
- Counts: pass=4, partial=1, missing=0, fail=0
- Retune targets: C-05
- Preserved pass criteria: C-01, C-02, C-03, C-04
- Hard gate alert: none

## Criteria
- C-01 Endpoint contract: pass. Reason: Summarized evidence satisfies the criterion. Evidence summary: The fixture exposes POST /api/widgets and tests the 201 response with widget fields. Evidence: examples/source-code-endpoint/src/server.js, examples/source-code-endpoint/test/server.test.js
- C-02 Input validation: pass. Reason: Summarized evidence satisfies the criterion. Evidence summary: The validation branch rejects missing, empty, or non-string names and tests the 400 response. Evidence: examples/source-code-endpoint/src/server.js, examples/source-code-endpoint/test/server.test.js
- C-03 Data integrity: pass. Reason: Summarized evidence satisfies the criterion. Evidence summary: The response includes id, name, and createdAt fields for created widgets. Evidence: examples/source-code-endpoint/src/server.js, examples/source-code-endpoint/test/server.test.js
- C-04 Test coverage: pass. Reason: Summarized evidence satisfies the criterion. Evidence summary: The fixture has focused node:test coverage for health, valid create, and invalid create behavior. Evidence: examples/source-code-endpoint/test/server.test.js
- C-05 Maintainability: partial. Reason: Evidence is present but incomplete. Evidence summary: The implementation is small and dependency-free, but the maintainability evidence should be stated more explicitly in the report. Evidence: examples/source-code-endpoint/src/server.js Retune: Clarify the maintainability evidence while keeping the implementation unchanged.

## Probes
- C-01: probe_skipped
- C-02: probe_skipped
- C-03 skipped: supporting criterion skipped by default selective policy
- C-04 skipped: supporting criterion skipped by default selective policy
- C-05 skipped: supporting criterion skipped by default selective policy

## Next action
Run the retune goal for failed, partial, or missing-evidence criteria only.

## App actions
- retune_failed_criteria: use retune_goal.md for the listed targets only.
- review_current_diff: inspect the current implementation before changing preserved pass criteria.
- mark_manual_evidence: attach summarized evidence without storing raw output.
