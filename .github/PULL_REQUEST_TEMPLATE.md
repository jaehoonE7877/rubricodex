<!--
  Rubricodex PR 템플릿. 해당 없는 섹션은 지워도 됩니다.
  연관 이슈가 있다면 본문에 `Closes #N`을 포함해주세요.
-->

## 설명

<!-- 무엇을 변경했는지 1~3줄로. -->

## 동기

<!-- 왜 이 변경이 필요한가? 어떤 문제를 푸는가? -->

## 추적

- Notion Spec / Contract:
- Linear Issue:
- GitHub Issue:
- Codex review:

## 변경 종류

- [ ] 🐞 버그 수정
- [ ] ✨ 신규 기능
- [ ] 💥 Breaking change
- [ ] 📝 문서 / repo meta

## 테스트 방법

```bash
# 예: 문서-only 변경이면 아래 검증 결과를 적어주세요.
rg -n "Rubricodex|rubricodex|\\.rubricodex/" README.md examples .github

# 코드 또는 hook 변경이면 아래 검증 결과를 적어주세요.
git show --check --pretty=format: HEAD
python3 -m unittest discover -s tests
python3 -m pytest -q
```

<!-- 위 외에 수동으로 확인한 시나리오가 있다면 적어주세요. -->

## 체크

- [ ] README가 Notion Canonical SSoT를 가리킨다.
- [ ] 로컬에 경쟁 SSoT 문서가 없다.
- [ ] schema · CLI command · artifact shape · taskpack wording을 바꿨다면 SSoT를 먼저 갱신했다.
- [ ] Legacy 제품명은 migration 설명에만 남아 있다.
- [ ] `.rubricodex/`, `rubricodex`, `Rubricodex` 용어가 일관적이다.
- [ ] Linear 이슈와 Notion 구현 현황에 PR/검증 근거를 연결했다.
- [ ] push 이후 PR 생성 전 Codex review를 확인했다.
