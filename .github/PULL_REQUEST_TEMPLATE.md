<!--
  Rubricodex PR 템플릿. 해당 없는 섹션은 지워도 됩니다.
  연관 이슈가 있다면 본문에 `Closes #N`을 포함해주세요.
-->

## 설명

<!-- 무엇을 변경했는지 1~3줄로. -->

## 동기

<!-- 왜 이 변경이 필요한가? 어떤 문제를 푸는가? -->

## 변경 종류

- [ ] 🐞 버그 수정
- [ ] ✨ 신규 기능
- [ ] 💥 Breaking change
- [ ] 📝 문서 / repo meta

## 테스트 방법

```bash
# 예: 문서-only 변경이면 아래 검증 결과를 적어주세요.
rg -n "Rubricodex|rubricodex|\\.rubricodex/" README.md docs .github
```

<!-- 위 외에 수동으로 확인한 시나리오가 있다면 적어주세요. -->

## 체크

- [ ] README가 `docs/rubricodex-ssot.md`를 가리킨다.
- [ ] SSoT의 이미지 링크가 `assets/rubricodex-harness-map.png`와 맞는다.
- [ ] schema · CLI command · artifact shape · taskpack wording을 바꿨다면 SSoT를 먼저 갱신했다.
- [ ] Legacy 제품명은 migration 설명에만 남아 있다.
- [ ] `.rubricodex/`, `rubricodex`, `Rubricodex` 용어가 일관적이다.
