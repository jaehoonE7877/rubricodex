# Rubricodex Lifecycle Hooks

Last verified: 2026-05-12

## Official support result

OpenAI Codex docs confirm that lifecycle hooks are enabled by `[features] codex_hooks = true`, loaded from `hooks.json` or inline `[hooks]`, and can be bundled by installed plugins through manifest `hooks` or default `./hooks/hooks.json`.

The Build plugins docs confirm that `.codex-plugin/plugin.json` can point `hooks` to lifecycle JSON relative to the plugin root. The Hooks docs also state that hook commands run with the session `cwd`, so Rubricodex does not assume plugin-root script execution.

## Design decision

Rubricodex uses phase-transition gates, not git hooks and not broad tool-call surveillance.

The bundled hook config is safe for plugin-only installs:

- If the `rubricodex` CLI is on `PATH`, hooks call `rubricodex hook gate ...`.
- If the CLI is not installed, hooks exit successfully without output.
- Hook code inspects prompt/artifact state in memory and does not store raw prompts, transcripts, logs, command output, secrets, or private data.

## Implemented gates

1. `rubricodex_intake_boundary_gate`
   - Event: `UserPromptSubmit`
   - CLI gate: `rubricodex hook gate intake-boundary`
   - Blocks requests that ask Rubricodex to store raw transcripts, task logs, or unredacted command output.
   - Adds intake guidance for Rubricodex prompts.

2. `rubricodex_matrix_readiness_gate`
   - Event: `UserPromptSubmit`
   - CLI gate: `rubricodex hook gate matrix-readiness`
   - Blocks implementation handoff language when required intent, matrix, goal, prompt lint, or matrix lock artifacts are missing or stale.

3. `rubricodex_completion_claim_gate`
   - Event: `Stop`
   - CLI gate: `rubricodex hook gate completion-claim`
   - Continues the turn when a completion claim is made but run artifacts are missing, invalid, or incomplete.

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
