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
- App-first artifacts store only summarized session state, decisions, card refs, and shared report/retune links.
- `rubricodex plan draft` is for a fresh or unlocked root; it refuses to overwrite an existing locked taskpack contract.
- `rubricodex plan draft --propose` may call a read-only Codex subagent for a grounded matrix draft. If the subagent fails or returns invalid JSON, keep deterministic fallback behavior.
- `rubricodex plan draft --review` confirms the matrix before lock. In non-interactive standard/strict/audit runs, use `--yes` or `--no` explicitly.
- `rubricodex evidence sketch` writes `evidence.draft.json`; it promotes to `evidence.json` only after confirmation.
- `rubricodex retune apply` creates a new taskpack from `retune_goal.md` and preserves pass criteria from the parent scorecard.
- The plugin is hook-ready through official Codex lifecycle config. Bundled hooks call `rubricodex hook gate ...` only when the local CLI is available; otherwise they exit successfully without output.

## Flow

1. Classify the request as `micro`, `quick`, `standard`, `strict`, or `audit`.
2. For natural-language starts, run `rubricodex plan draft --run-id <run-id> --goal "<goal>" --propose --review --yes` when a grounded, confirmed matrix is needed.
3. For Codex app entry, write or import `.rubricodex/app/sessions/<session-id>/app-session.json` and `cards.json`.
4. Write or validate `.rubricodex/intent/brief.json`.
5. Write or validate `.rubricodex/matrix/evaluation-matrix.json`.
6. Run `rubricodex app session import --from <app-session.json>` when the request began in the app.
7. Run `rubricodex goal compile --run-id <run-id>` to create `goal.md`, `adapter-input.json`, and `goal.lock.json` when the draft command was not used.
8. Run `rubricodex prompt lint --run-id <run-id>`.
9. Run `rubricodex matrix lock --run-id <run-id>` before implementation and again before scoring when standard/strict/audit criteria must not drift.
10. Implement the task or collect the completed implementation references.
11. Run `rubricodex evidence sketch --run-id <run-id> --changed-file <path> --yes` or save summarized evidence in `.rubricodex/runs/<run-id>/evidence.json` before scoring.
12. Run `rubricodex orchestrate run --run-id <run-id>` to create local handoff, probe, scorecard, report, retune, and app collection artifacts from the current evidence.
13. Use lower-level `run local`, `probe plan`, `probe run`, `score compute`, and `report` commands only when debugging a single phase.
14. Run `rubricodex orchestrate status --run-id <run-id>` and `rubricodex app collect --run-id <run-id>` to verify app/local artifacts share the same report and retune instruction.
15. If retune is needed, run `rubricodex retune apply --run-id <run-id>` and preserve pass criteria listed in the retune `Exclude` section unless the user explicitly approves a scope change.

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
- Evidence draft: `.rubricodex/runs/<run_id>/evidence.draft.json`
- Scorecard: `.rubricodex/runs/<run_id>/scorecard.json`
- Report: `.rubricodex/runs/<run_id>/report.md`
- Retune instruction: `.rubricodex/runs/<run_id>/retune_goal.md`
- App session: `.rubricodex/app/sessions/<session_id>/app-session.json`
- App cards: `.rubricodex/app/sessions/<session_id>/cards.json`
- App collection: `.rubricodex/runs/<run_id>/app-collection.json`
- Orchestrator: `.rubricodex/runs/<run_id>/orchestrator.json`
- Hook design: `plugins/rubricodex/HOOKS.md`

## App Actions

- `retune_failed_criteria`: run the generated retune goal for listed criteria only.
- `review_current_diff`: inspect current changes before touching preserved pass criteria.
- `mark_manual_evidence`: attach summarized evidence without raw command output.

## Score Model

v0.1 uses `counts-v0.1`: each criterion is `pass`, `partial`, `missing_evidence`, or `fail`. Do not use weighted `total_score` or `threshold` fields in v0.1 scorecards.
