# Source Code Endpoint Fixture

이 fixture는 Rubricodex v0.1의 수동 `@Rubricodex` mention playbook을 검증합니다. 실제 Codex app plugin, CLI runner, schema validation 없이도 target, matrix, taskpack, scorecard/report가 한 흐름으로 이어지는지 보여줍니다.

## Example Mention

```text
@Rubricodex 우리 서비스에 POST /api/widgets endpoint를 추가해줘. 너무 무겁게 말고 기본 테스트까지.
```

## Manual Harness Flow

1. Harness Plan Card를 작성합니다.
   - Mode: `standard`
   - Why this mode: endpoint 추가와 테스트가 필요하지만 결제, 권한, migration은 없습니다.
   - Target: `POST /api/widgets`가 valid input을 받아 widget을 생성하고 `201` 응답을 반환합니다.
   - Questions: 없음. fixture 범위에서 repo convention으로 충분합니다.
   - Criteria: endpoint contract, input validation, data integrity, test coverage, maintainability
   - Evidence: `npm test`
   - Next action: taskpack implementation prompt 실행
2. `.rubricodex/target.json`과 `.rubricodex/matrix.json`으로 성공 기준을 고정합니다.
3. `.rubricodex/taskpacks/example-v0.1/implement.md`를 Codex app 작업 prompt로 사용합니다.
4. 구현 후 `.rubricodex/taskpacks/example-v0.1/review-all.md`로 결과를 검토합니다.
5. `.rubricodex/runs/example-v0.1/scorecard.json`과 `report.md`에 pass/fail/missing evidence를 기록합니다.

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
