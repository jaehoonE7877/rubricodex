# 보안 정책

## 지원 버전

가장 최신 minor 라인만 보안 패치를 받습니다. 이전 라인은 별도 backport 요청이 없는 한 패치하지 않습니다.

| 버전 | 보안 패치 |
|---|---|
| main / unreleased | ✅ |
| older drafts | ❌ |

## 취약점 신고

**공개 GitHub Issue를 만들지 말아주세요.** 취약점은 비공개 채널로 알려주시면 가능한 한 빨리 대응하겠습니다.

다음 중 한 가지 방법을 선택해주세요.

1. **GitHub Security Advisories** (권장) — [Report a vulnerability](https://github.com/jaehoonE7877/rubricodex/security/advisories/new) 페이지에서 비공개로 제출.
2. **이메일** — `sjh7877@naver.com`. 메일 제목에 `[Rubricodex Security]`를 붙여주세요.

가능하면 다음을 함께 보내주세요.

- 영향받는 Rubricodex 버전
- 재현 절차 (최소 PoC 권장)
- 예상 영향 범위 (RCE / 데이터 노출 / 권한 우회 등)
- 패치 제안 (선택)

## 응답 SLA (best-effort)

- **48시간 이내**: 신고 확인 회신
- **7일 이내**: 영향 범위 평가 및 트리아지 등급 회신
- **30일 이내**: 수정 또는 미티게이션 계획 공유

긴급(actively exploited) 신고는 우선 순위로 처리합니다.

## 공개 시점

- 패치가 배포되고 충분한 사용자가 업그레이드한 뒤 GitHub Security Advisory로 공개합니다.
- 신고자가 원하면 advisory에 credit을 표기합니다.
