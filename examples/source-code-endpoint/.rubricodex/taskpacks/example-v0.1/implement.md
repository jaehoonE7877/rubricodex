# Implement Source Code Endpoint Fixture

You are implementing the Rubricodex v0.1 source-code-endpoint fixture.

## Target

Build a minimal Node.js endpoint fixture where:

- `GET /health` returns `200` with `{"ok":true}`.
- `POST /api/widgets` accepts JSON with a non-empty `name`.
- Valid widget creation returns `201` with `{"widget":{"id":"<id>","name":"<trimmed name>"}}`.
- Missing or blank names return `400` with a clear error.
- Unknown routes return `404`.

## Constraints

- Use Node.js built-in modules only.
- Keep the implementation small and explicit.
- Do not add framework dependencies.
- Do not implement Rubricodex app plugin, CLI automation, matrix lock hashing, or automated probes.
- Do not create a local SSoT document.

## Evidence

Run:

```bash
npm test
```
