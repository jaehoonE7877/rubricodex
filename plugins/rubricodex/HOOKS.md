# Rubricodex Lifecycle Hooks

Last verified: 2026-05-12
v1.0.3 policy aligned: 2026-05-13

## Official support result

OpenAI Codex docs confirm that lifecycle hooks are enabled by `[features] codex_hooks = true`, loaded from `hooks.json` or inline `[hooks]`, and can be bundled by installed plugins through manifest `hooks` or default `./hooks/hooks.json`.

The Build plugins docs confirm that `.codex-plugin/plugin.json` can point `hooks` to lifecycle JSON relative to the plugin root. The Hooks docs also state that hook commands run with the session `cwd`, so Rubricodex does not assume plugin-root script execution.

## Design decision

Rubricodex uses small lifecycle glue and deterministic guards, not git hooks,
broad tool-call surveillance, or a natural-language policy parser.

The bundled hook config is safe for plugin-only installs:

- If the `rubricodex` CLI is on `PATH`, hooks call `rubricodex hook gate ...`.
- If the CLI is not installed, hooks exit successfully without output.
- Hook code inspects prompt/artifact state in memory and does not store raw
  prompts, transcripts, logs, command output, secrets, or private data.
- Hook output must not echo the user's prompt. When raw storage risk is detected,
  it returns classification-based guidance only.
- Raw transcript, raw log, and unredacted command output storage prevention is
  enforced by artifact schema validation, validators, and report writer
  contracts. Validators reject forbidden raw fields and raw-content markers in
  artifact string values. Hooks are only an early guidance layer.

## Implemented gates

1. `rubricodex_intake_boundary_gate`
   - Event: `UserPromptSubmit`
   - CLI gate: `rubricodex hook gate intake-boundary`
   - Never hard-blocks first `@Rubricodex` prompts, AGENTS.md/policy prompts, or
     raw storage requests.
   - Adds short intake guidance for Rubricodex prompts.
   - If raw artifact storage risk is detected, returns safe guidance without the
     prompt text and lets artifact validators reject forbidden raw artifacts.

2. `rubricodex_matrix_readiness_gate`
   - Event: `UserPromptSubmit`
   - CLI gate: `rubricodex hook gate matrix-readiness`
   - Does not block first-run prompts or implementation-like prompts with no
     taskpack/run state.
   - Blocks only when implementation handoff is explicit and a deterministic
     taskpack/run id exists but required intent, matrix, goal, prompt lint, or
     matrix lock artifacts are missing or stale.

3. `rubricodex_completion_claim_gate`
   - Event: `Stop`
   - CLI gate: `rubricodex hook gate completion-claim`
   - Ignores generic status phrases such as test-passed statements.
   - Continues the turn only when an explicit completion claim is made while an
     active Rubricodex run has missing, invalid, or incomplete artifacts.

## Operator setup

Hooks require Codex hook support to be enabled by the user or environment:

```toml
[features]
codex_hooks = true
```

For full gate enforcement in a repo, install the CLI locally:

```bash
python3 -m pip install -e .
```

Without the CLI, the plugin remains usable through its bundled skill and the hook commands fail open.
