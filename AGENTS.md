# Agent Instructions

## Source of Truth

- 제품 방향, UX, roadmap, policy, schema, CLI command, artifact shape, score model, backend policy, example, taskpack wording은 Notion의 `Rubricodex Canonical SSoT`가 canonical source입니다.
- Notion Canonical SSoT: https://app.notion.com/p/3544408817af8182b23ecf3ba169d82e
- 로컬 repo에는 별도 SSoT mirror를 두지 않습니다. 제품 기준을 바꾸기 전에 Notion SSoT를 먼저 확인하고, 변경이 필요하면 Notion을 먼저 갱신합니다.
- 경쟁하는 spec 또는 architecture 문서를 새로 만들지 않습니다. 새 설명이 필요하면 Notion SSoT, Specs/RFC, Decision Log 중 맞는 운영 표면에 추가합니다.
- 새 파일에서는 공식 이름 `Rubricodex`, 공식 artifact directory `.rubricodex/`, 공식 CLI prefix `rubricodex`를 사용합니다. Legacy `Rubrix` 명칭은 migration 설명에서만 허용합니다.

## Repo Map

- `README.md`: 짧은 프로젝트 입구입니다. Rubricodex 핵심 가치, 기본 사용법, Notion Canonical SSoT 링크만 유지합니다.
- `plugins/rubricodex/assets/`: README와 Codex plugin marketplace에서 사용하는 Rubricodex icon 자산을 둡니다.
- `.rubricodex/`: 이후 CLI/example이 생성할 runtime artifact 기준 경로입니다. 현재 없더라도 다른 이름으로 대체하지 않습니다.

## Change Rules

- 작고 명시적이며 유지보수하기 쉬운 변경을 선호합니다.
- Notion Canonical SSoT, 구현, README, examples, schema, taskpack이 충돌하면 먼저 제품 결정을 Notion에서 확정하고 repo 구현/문서를 같은 변경에서 맞춥니다.
- Schema, CLI command, artifact shape, score model, backend policy를 바꾸는 작업은 Notion Canonical SSoT와 Contract Index를 먼저 갱신합니다.
- Raw chat transcript는 이 repo에 저장하지 않습니다. 필요한 경우 요약된 evidence, reference, 결정사항만 남깁니다.

## Notion Operating Rules

Rubricodex Notion은 전문 제품조직 수준의 운영 표면으로 관리합니다.

- Canonical SSoT, Roadmap, Specs/RFCs, Decision Log/ADRs, Implementation Tracker, Contract Index, Dashboard의 역할을 분리합니다.
- 제품 방향이나 계약 변경은 Canonical SSoT에 먼저 반영하고, 실행 항목은 Roadmap/Tracker로 분리합니다.
- 큰 변경은 Specs/RFC에 문제, 제안, non-goals, open questions, 완료 기준을 짧게 남깁니다.
- 결정은 Decision Log/ADR에 남기고, Accepted 결정은 덮어쓰지 않습니다. 바뀌면 superseding ADR을 만듭니다.
- 계약성 항목(schema, CLI, artifact, taskpack, report)은 Contract Index에 `Status`, `Contract Type`, `Canonical Repo Path`, `Current Version`, `Last Verified`를 유지합니다.
- 실행 항목은 DRI, Status, Priority, Risk, Done Criteria, Verification Evidence를 둡니다.
- 문서는 한국어로 짧고 명확하게 씁니다. 독자가 바로 실행해야 할 것과 판단해야 할 것을 먼저 보이게 합니다.
- 상태값은 실제 진행 상태와 맞춥니다. 완료는 evidence가 있을 때만 Done/Verified로 둡니다.
- Dashboard는 원본 데이터를 복제하지 않고 linked database/view로 보여줍니다.
- raw transcript, raw task log, redaction되지 않은 command output, 개인/민감정보는 저장하지 않습니다.
- Notion 페이지가 길어지면 요약과 운영 필드만 남기고 상세는 Specs/RFC 또는 Contract Index로 분리합니다.

## Ask First

다음 작업은 시작 전에 사용자 확인을 받습니다.

- `.rubricodex/` artifact 계약의 breaking change
- 생성 이미지 asset 삭제 또는 기존 asset 덮어쓰기
- raw transcript, log, unredacted command output을 repo에 저장하는 변경
- `Rubricodex`에서 다른 제품명으로 canonical naming 변경

## Validation

문서나 asset을 바꾼 뒤에는 최소한 아래를 확인합니다.

- `README.md`가 Notion Canonical SSoT를 가리키는지 확인합니다.
- 로컬에 `docs/rubricodex-ssot.md` 같은 경쟁 SSoT가 다시 생기지 않았는지 확인합니다.
- Legacy `Rubrix` 명칭은 migration 설명에만 남아 있는지 확인합니다.
- `.rubricodex/`, `rubricodex`, `Rubricodex` 용어가 새 문서와 예제에서 일관적인지 확인합니다.
