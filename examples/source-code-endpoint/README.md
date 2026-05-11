# Source Code Endpoint Fixture

이 fixture는 Rubricodex의 app-first/local CLI flow를 검증합니다. `app-session.json`, `cards.json`, `brief.json`, `evaluation-matrix.json`, `goal.md`, `goal.lock.json`, `run-manifest.json`, `probe-plan.json`, probe results, `evidence.json`, `scorecard.json`, `report.md`, `retune_goal.md`가 한 흐름으로 이어지는지 보여줍니다.

## Example Mention

```text
@Rubricodex 우리 서비스에 POST /api/widgets endpoint를 추가해줘. 너무 무겁게 말고 기본 테스트까지.
```

## Harness Flow

1. `.rubricodex/intent/brief.json`에 bounded request를 고정합니다.
2. `.rubricodex/matrix/evaluation-matrix.json`에 GQE-R-lite 기준을 고정합니다.
3. `.rubricodex/app/sessions/example-session/app-session.json`과 `cards.json`은 Codex app 표면이 넘겨야 할 요약 입력과 UI 카드 참조를 보여줍니다.
4. `rubricodex app session import --from .../app-session.json`로 app session을 run artifact에 연결합니다.
5. `rubricodex goal compile --run-id example-v0.1`로 taskpack을 생성합니다.
6. `rubricodex prompt lint --run-id example-v0.1`로 실행 prompt를 확인합니다.
7. `rubricodex matrix lock --run-id example-v0.1`로 기준 drift를 확인합니다.
8. 구현 후 `.rubricodex/runs/example-v0.1/evidence.json`에 요약 evidence만 기록합니다.
9. `rubricodex orchestrate run --run-id example-v0.1 --parallel 2`로 local handoff, probes, scorecard, report, retune, app collection을 현재 evidence 기준으로 갱신합니다.
10. `rubricodex orchestrate status --run-id example-v0.1`와 `rubricodex app collect --run-id example-v0.1`로 app/local artifact가 같은 report와 retune instruction을 참조하는지 확인합니다. `retune_goal.md`는 failed/partial/missing_evidence 기준만 다시 시도하고 pass 기준은 보존 목록으로 보호합니다.

v1.0 natural-language start는 같은 경로를 직접 생성합니다:

```bash
python3 -m rubricodex.cli --root examples/source-code-endpoint plan draft --run-id example-v1.0 --goal "Add a POST /api/widgets endpoint with tests and summarized evidence."
```

## Modes

| Mode | v0.1 expected behavior |
| --- | --- |
| `micro` | 질문 없이 inline check 1-2개만 둡니다. |
| `quick` | 질문 0-1개, criteria 2-3개로 끝냅니다. |
| `standard` | 질문 1-3개 이하, criteria 4-6개, 필요한 evidence를 명시합니다. |
| `strict` | 결제, 권한, 개인정보, 데이터 무결성처럼 hard gate가 필요한 경우에만 씁니다. |
| `audit` | 구현 없이 diff/result를 scorecard로 검토합니다. |

## Run

```bash
python3 -m rubricodex.cli --root examples/source-code-endpoint goal compile --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint prompt lint --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint matrix lock --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint app session import --from examples/source-code-endpoint/.rubricodex/app/sessions/example-session/app-session.json
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate run --run-id example-v0.1 --parallel 2
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate status --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint app collect --run-id example-v0.1
npm test
npm start
```

Server:

- `GET /health`
- `POST /api/widgets`

Valid request:

```bash
curl -s http://localhost:3000/api/widgets \
  -H 'content-type: application/json' \
  -d '{"name":"alpha"}'
```
