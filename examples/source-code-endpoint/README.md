# Source Code Endpoint Fixture

이 fixture는 Rubricodex의 local plugin-style CLI flow를 검증합니다. `brief.json`, `evaluation-matrix.json`, `goal.md`, `goal.lock.json`, `run-manifest.json`, `evidence.json`, `scorecard.json`, `report.md`, `retune_goal.md`가 한 흐름으로 이어지는지 보여줍니다.

## Example Mention

```text
@Rubricodex 우리 서비스에 POST /api/widgets endpoint를 추가해줘. 너무 무겁게 말고 기본 테스트까지.
```

## Harness Flow

1. `.rubricodex/intent/brief.json`에 bounded request를 고정합니다.
2. `.rubricodex/matrix/evaluation-matrix.json`에 GQE-R-lite 기준을 고정합니다.
3. `rubricodex goal compile --run-id example-v0.1`로 taskpack을 생성합니다.
4. `rubricodex prompt lint --run-id example-v0.1`로 실행 prompt를 확인합니다.
5. `rubricodex matrix lock --run-id example-v0.1`로 기준 drift를 확인합니다.
6. `rubricodex run local --run-id example-v0.1`로 Codex CLI handoff manifest를 생성합니다.
7. 구현 후 `.rubricodex/runs/example-v0.1/evidence.json`에 요약 evidence만 기록합니다.
8. `rubricodex score compute --run-id example-v0.1`와 `rubricodex report --run-id example-v0.1`로 scorecard/report/retune instruction을 생성합니다.

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
python3 -m rubricodex.cli --root examples/source-code-endpoint run local --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint score compute --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint report --run-id example-v0.1
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
