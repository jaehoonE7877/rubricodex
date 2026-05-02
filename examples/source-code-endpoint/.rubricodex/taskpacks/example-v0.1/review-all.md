# Review Source Code Endpoint Fixture

Review the implementation against the matrix in `examples/source-code-endpoint/.rubricodex/matrix.json`.

## Required Checks

- Confirm valid `POST /api/widgets` input returns `201`.
- Confirm blank or missing `name` returns `400`.
- Confirm tests cover health, creation, validation failure, and unknown routes.
- Confirm the fixture uses no runtime dependencies.
- Confirm no raw transcript, raw task log, or competing local SSoT document was added.

## Evidence

Run:

```bash
npm test
```

Record pass/fail/missing evidence in `.rubricodex/runs/example-v0.1/scorecard.json` and summarize in `report.md`.
