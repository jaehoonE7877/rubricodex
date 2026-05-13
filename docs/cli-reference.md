# Rubricodex CLI Reference

이 문서는 로컬에서 `rubricodex` 명령을 바로 쓰기 위한 실행 참고서입니다. 제품 방향, schema 의미, artifact 계약의 canonical source는 Notion Canonical SSoT입니다.

## 설치

```bash
python3 -m pip install -e .
rubricodex --help
```

설치 없이 repo 안에서 실행할 때는 `rubricodex` 대신 `python3 -m rubricodex.cli`를 사용합니다.

## 기본 흐름

```bash
rubricodex init
rubricodex plan draft --run-id <run-id> --goal "<goal>"
rubricodex intent validate
rubricodex matrix validate
rubricodex prompt lint --run-id <run-id>
rubricodex matrix lock --run-id <run-id>
```

`plan draft`는 fresh 또는 unlocked root에서 intent brief, evaluation matrix, taskpack, prompt lint, matrix lock을 한 번에 만듭니다. 이미 locked taskpack이 있으면 기존 계약을 덮어쓰지 않고 실패합니다.

## 구현 후 검증

```bash
rubricodex evidence validate --run-id <run-id>
rubricodex score compute --run-id <run-id>
rubricodex score validate --run-id <run-id>
rubricodex report --run-id <run-id>
```

전체 local harness 흐름은 orchestrator로 실행합니다.

```bash
rubricodex orchestrate run --run-id <run-id> --parallel 2
rubricodex orchestrate status --run-id <run-id>
```

local runner는 기본적으로 dry-run handoff만 기록합니다. 실제 Codex CLI 실행은 `--execute`를 명시할 때만 시도합니다.

## App artifacts

Codex app에서 시작한 작업은 app session과 cards를 공유 run artifact에 연결합니다.

```bash
rubricodex app session validate --file .rubricodex/app/sessions/<session-id>/app-session.json
rubricodex app cards validate --file .rubricodex/app/sessions/<session-id>/cards.json
rubricodex app session import --from .rubricodex/app/sessions/<session-id>/app-session.json
rubricodex app collect --run-id <run-id>
```

App artifacts는 raw transcript를 저장하지 않습니다. 저장되는 것은 summarized session state, selected refs, decisions refs, cards, report/retune refs입니다.

## JSON Schemas

Core v0.1 artifact schemas는 package data로 포함됩니다.

```bash
rubricodex schema list
rubricodex schema path --artifact-type rubricodex.evaluation_matrix
rubricodex schema show --artifact-type rubricodex.evaluation_matrix
```

Schemas는 자동화와 문서화를 위한 lightweight surface입니다. 실제 enforcement는 현재 Python validators가 맡습니다.

## Lifecycle hooks

Plugin-bundled lifecycle hooks는 CLI가 설치되어 있을 때만 phase gate를 실행합니다.
`intake-boundary`는 `UserPromptSubmit`에서 hard block하지 않고 advisory `additionalContext`를 제공합니다. raw transcript/log/command output 저장 위험이 보이면 prompt 원문 없이 gate 이름과 원인 분류를 guidance에 포함합니다. 실제 raw 저장 방지는 artifact schema와 Python validators가 맡습니다.

```bash
rubricodex hook gate intake-boundary
rubricodex hook gate matrix-readiness
rubricodex hook gate completion-claim
```

Codex hook event에서는 JSON payload가 stdin으로 전달됩니다. 직접 확인할 때는 예시 payload를 넣을 수 있습니다.

```bash
printf '{"prompt":"@Rubricodex implement now","cwd":"%s"}' "$PWD" \
  | rubricodex hook gate matrix-readiness
```

자세한 hook 결정은 [plugins/rubricodex/HOOKS.md](../plugins/rubricodex/HOOKS.md)를 봅니다.

## Example fixture

Repo fixture를 바로 검증하는 명령입니다.

```bash
python3 -m rubricodex.cli --root examples/source-code-endpoint intent validate
python3 -m rubricodex.cli --root examples/source-code-endpoint matrix validate
python3 -m rubricodex.cli --root examples/source-code-endpoint prompt lint --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint matrix lock --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate run --run-id example-v0.1 --parallel 2
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate status --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint app collect --run-id example-v0.1
```

Node fixture 테스트:

```bash
cd examples/source-code-endpoint
npm test
```
