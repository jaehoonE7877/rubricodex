# Agent Instructions

## Source of Truth

- 제품 동작, schema, CLI command, example, taskpack wording을 바꾸기 전에 `docs/rubricodex-ssot.md`를 먼저 읽습니다.
- `docs/rubricodex-ssot.md`가 canonical source입니다. 제품 방향이 바뀌면 SSoT를 먼저 수정하고, `README.md`, example, schema, taskpack은 그 뒤에 맞춥니다.
- 경쟁하는 spec 또는 architecture 문서를 새로 만들지 않습니다. 새 설명이 필요하면 SSoT 안에 섹션을 추가합니다.
- 새 파일에서는 공식 이름 `Rubricodex`, 공식 artifact directory `.rubricodex/`, 공식 CLI prefix `rubricodex`를 사용합니다. Legacy `Rubrix` 명칭은 migration 설명에서만 허용합니다.

## Repo Map

- `README.md`: 짧은 프로젝트 입구입니다. SSoT 링크와 한 줄 설명만 유지합니다.
- `docs/rubricodex-ssot.md`: 제품 스펙, 아키텍처, 주요 개념, artifact 계약, roadmap의 단일 기준입니다.
- `assets/`: SSoT에서 참조하는 문서용 이미지 자산을 둡니다.
- `.rubricodex/`: 이후 CLI/example이 생성할 runtime artifact 기준 경로입니다. 현재 없더라도 다른 이름으로 대체하지 않습니다.

## Change Rules

- 작고 명시적이며 유지보수하기 쉬운 변경을 선호합니다.
- SSoT와 구현 또는 문서가 충돌하면 SSoT를 기준으로 맞춥니다. SSoT가 틀렸다면 같은 변경에서 SSoT도 함께 고칩니다.
- Schema, CLI command, artifact shape, score model, backend policy를 바꾸는 작업은 SSoT의 관련 섹션을 먼저 갱신합니다.
- Raw chat transcript는 이 repo에 저장하지 않습니다. 필요한 경우 요약된 evidence, reference, 결정사항만 남깁니다.

## Ask First

다음 작업은 시작 전에 사용자 확인을 받습니다.

- `docs/rubricodex-ssot.md` 삭제, 이름 변경, 또는 대체
- `.rubricodex/` artifact 계약의 breaking change
- 생성 이미지 asset 삭제 또는 기존 asset 덮어쓰기
- raw transcript, log, unredacted command output을 repo에 저장하는 변경
- `Rubricodex`에서 다른 제품명으로 canonical naming 변경

## Validation

문서나 asset을 바꾼 뒤에는 최소한 아래를 확인합니다.

- `README.md`가 `docs/rubricodex-ssot.md`를 가리키는지 확인합니다.
- SSoT의 이미지 링크가 `assets/rubricodex-harness-map.png`와 맞는지 확인합니다.
- Legacy `Rubrix` 명칭은 migration 설명에만 남아 있는지 확인합니다.
- `.rubricodex/`, `rubricodex`, `Rubricodex` 용어가 새 문서와 예제에서 일관적인지 확인합니다.
