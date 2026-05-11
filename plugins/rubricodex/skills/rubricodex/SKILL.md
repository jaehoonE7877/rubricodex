---
name: rubricodex
description: Use when a Codex implementation request is ambiguous and needs to be compressed into a bounded target, evaluation matrix, taskpack, evidence, scorecard/report, and retune instruction.
---

# Rubricodex

Rubricodex is a local Codex output-quality harness. Use it to turn a vague implementation request into a small, testable contract before implementation, then score the result from summarized evidence.

## Operating Rules

- Canonical product decisions live in the Notion Rubricodex Canonical SSoT.
- Use the official names `Rubricodex`, `.rubricodex/`, and `rubricodex`.
- Do not store raw transcripts, raw task logs, or unredacted command output in repo artifacts or Notion.
- v0.1 is a plugin-style skill plus local CLI. It does not directly run Codex CLI or app internals.

## Flow

1. Classify the request as `micro`, `quick`, `standard`, `strict`, or `audit`.
2. Write or validate `.rubricodex/intent/brief.json`.
3. Write or validate `.rubricodex/matrix/evaluation-matrix.json`.
4. Run `rubricodex goal compile --run-id <run-id>` to create `goal.md`, `adapter-input.json`, and `goal.lock.json`.
5. Run `rubricodex prompt lint --run-id <run-id>`.
6. After implementation, save summarized evidence in `.rubricodex/runs/<run-id>/evidence.json`.
7. Run `rubricodex score compute --run-id <run-id>`.
8. Run `rubricodex report --run-id <run-id>` and use `retune_goal.md` only for failed, partial, or missing criteria.

## Artifact Contract

- Intent brief: `.rubricodex/intent/brief.json`
- Matrix: `.rubricodex/matrix/evaluation-matrix.json`
- Taskpack: `.rubricodex/taskpacks/<run_id>/goal.md`
- Evidence: `.rubricodex/runs/<run_id>/evidence.json`
- Scorecard: `.rubricodex/runs/<run_id>/scorecard.json`
- Report: `.rubricodex/runs/<run_id>/report.md`
- Retune instruction: `.rubricodex/runs/<run_id>/retune_goal.md`

## Score Model

v0.1 uses `counts-v0.1`: each criterion is `pass`, `partial`, `missing_evidence`, or `fail`. Do not use weighted `total_score` or `threshold` fields in v0.1 scorecards.
