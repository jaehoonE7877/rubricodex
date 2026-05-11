/goal Complete Rubricodex taskpack example-v0.1 using the bounded contract below.

## Purpose
Demonstrate Rubricodex v0.1 on a bounded source-code endpoint task.

## Desired outcome
POST /api/widgets accepts valid JSON input, creates an in-memory widget, and returns 201 with the widget payload.

## Deliverable
Small Express endpoint plus node:test coverage in the source-code-endpoint fixture.

## Context
- examples/source-code-endpoint/src/server.js
- examples/source-code-endpoint/test/server.test.js
- examples/source-code-endpoint/package.json

## Include
- POST /api/widgets
- name validation
- 201 response for valid input
- 400 response for invalid input
- node:test coverage

## Exclude
- database persistence
- authentication
- frontend UI
- external services

## Working rules
- Use the fixture's existing Node.js runtime.
- Do not add production dependencies.
- Store only summarized evidence, not raw command output.

## Evaluation
- C-01 (hard gate): Does POST /api/widgets return 201 with a created widget for valid JSON input? Evidence: Implementation reference for POST /api/widgets; Test reference for valid widget creation
- C-02 (hard gate): Does invalid input return 400 without creating a widget? Evidence: Implementation reference for validation branch; Test reference for missing or empty name
- C-03 (supporting): Does each created widget have stable id, name, and createdAt fields? Evidence: Implementation reference for widget creation; Test reference for response fields
- C-04 (supporting): Do fixture tests cover health, valid create, and invalid create behavior? Evidence: node:test references for health and widget flows
- C-05 (supporting): Is the implementation small and consistent with the fixture style? Evidence: Implementation summary confirming no heavy abstraction or new dependency

## Evidence
Store only summarized evidence references in `.rubricodex/runs/example-v0.1/evidence.json`.
Do not store raw transcripts, raw task logs, or unredacted command output.

## Completion rule
Finish only when hard gates pass and the report can cite summarized evidence for every criterion.
If a hard gate is missing or fails, stop with a retune instruction instead of calling the task complete.

## Report back
Return the scorecard decision, evidence summary, and next retune instruction if any.
