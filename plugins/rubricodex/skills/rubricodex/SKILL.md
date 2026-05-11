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
- The local runner records only a manifest and summarized evidence. Direct Codex CLI execution is opt-in via `rubricodex run local --execute`.

## Flow

1. Classify the request as `micro`, `quick`, `standard`, `strict`, or `audit`.
2. Write or validate `.rubricodex/intent/brief.json`.
3. Write or validate `.rubricodex/matrix/evaluation-matrix.json`.
4. Run `rubricodex goal compile --run-id <run-id>` to create `goal.md`, `adapter-input.json`, and `goal.lock.json`.
5. Run `rubricodex prompt lint --run-id <run-id>`.
6. Run `rubricodex matrix lock --run-id <run-id>` before implementation and again before scoring when standard/strict/audit criteria must not drift.
7. Run `rubricodex run local --run-id <run-id>` to create a dry-run handoff manifest, or add `--execute` only when direct Codex CLI execution is intended.
8. Run `rubricodex probe plan --run-id <run-id>` to select only useful read-only probes and record skip reasons.
9. Run `rubricodex probe run --run-id <run-id> --parallel <N>` to write normalized probe results, or add `--execute` only when direct Codex CLI probe execution is intended.
10. After implementation, save summarized evidence in `.rubricodex/runs/<run-id>/evidence.json`.
11. Run `rubricodex score compute --run-id <run-id>`.
12. Run `rubricodex report --run-id <run-id>` and use `retune_goal.md` only for failed, partial, or missing criteria.
13. Preserve pass criteria listed in the retune `Exclude` section unless the user explicitly approves a scope change.

## Artifact Contract

- Intent brief: `.rubricodex/intent/brief.json`
- Matrix: `.rubricodex/matrix/evaluation-matrix.json`
- Taskpack: `.rubricodex/taskpacks/<run_id>/goal.md`
- Matrix lock: `.rubricodex/taskpacks/<run_id>/goal.lock.json`
- Probe plan: `.rubricodex/taskpacks/<run_id>/probe-plan.json`
- Probe prompts: `.rubricodex/taskpacks/<run_id>/probes/<criterion_id>.md`
- Run manifest: `.rubricodex/runs/<run_id>/run-manifest.json`
- Probe results: `.rubricodex/runs/<run_id>/probes/<criterion_id>.json`
- Evidence: `.rubricodex/runs/<run_id>/evidence.json`
- Scorecard: `.rubricodex/runs/<run_id>/scorecard.json`
- Report: `.rubricodex/runs/<run_id>/report.md`
- Retune instruction: `.rubricodex/runs/<run_id>/retune_goal.md`

## App Actions

- `retune_failed_criteria`: run the generated retune goal for listed criteria only.
- `review_current_diff`: inspect current changes before touching preserved pass criteria.
- `mark_manual_evidence`: attach summarized evidence without raw command output.

## Score Model

v0.1 uses `counts-v0.1`: each criterion is `pass`, `partial`, `missing_evidence`, or `fail`. Do not use weighted `total_score` or `threshold` fields in v0.1 scorecards.
