<div align="center">
  <img src="./assets/codex-plugin/logo.png" alt="Rubricodex logo" width="128" />

  <h1>Rubricodex</h1>

  <p><strong>Codex 작업을 애매한 요청에서 검증 가능한 목표로 바꾸는 작은 harness</strong></p>

  <p>
    <a href="#codex-app에-설치"><strong>Codex app 설치</strong></a>
    ·
    <a href="#로컬-cli-설치"><strong>CLI 설치</strong></a>
    ·
    <a href="#어떻게-돌아가나"><strong>흐름</strong></a>
    ·
    <a href="#예시"><strong>예시</strong></a>
  </p>

  <p>
    <img alt="Codex plugin" src="https://img.shields.io/badge/Codex-plugin-2563EB" />
    <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB" />
    <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-111827" />
  </p>
</div>

---

## 한 줄로 말하면

Rubricodex는 Codex에게 일을 맡기기 전에 **무엇을 만들지**, **어떤 기준이면 성공인지**, **무엇으로 검증할지**를 짧게 고정합니다.

그래서 Codex가 “다 된 것 같아요”라고 말하는 대신, 아래처럼 확인 가능한 결과를 남기게 합니다.

| Codex 작업에서 자주 생기는 문제 | Rubricodex가 고정하는 것 | 쉬운 뜻 |
| --- | --- | --- |
| 완료 기준이 흐림 | `intent brief` | 무엇을 만들지 한 장으로 정리 |
| 성공 기준이 중간에 바뀜 | `evaluation matrix` | 합격 기준표 |
| 검증 근거가 부족함 | `evidence` | 테스트, 파일, 결과 요약 |
| 실패 후 다음 지시가 장황함 | `retune instruction` | 다시 시도할 짧은 지시 |

> [!IMPORTANT]
> Codex app 플러그인 설치와 `rubricodex` CLI 설치는 서로 다릅니다.
> app에서 `@Rubricodex`를 쓰려면 Marketplace에 플러그인을 추가해야 하고,
> 터미널에서 `rubricodex ...` 명령을 직접 쓰려면 Python CLI도 설치해야 합니다.

## Codex app에 설치

첨부한 화면 기준으로는 Marketplace를 먼저 추가한 뒤, 그 안에서 Rubricodex 플러그인을 설치하면 됩니다.

1. Codex app 왼쪽/상단의 Marketplace 선택 메뉴를 엽니다.
2. `+ 더 추가`를 누릅니다.
3. `마켓플레이스 추가` 창에 아래 값을 넣습니다.

| 입력 칸 | 값 |
| --- | --- |
| 출처 | `jaehoonE7877/rubricodex` |
| Git ref | `main` |
| Sparse 경로 | `.agents/plugins`<br />`plugins/rubricodex` |

4. `마켓플레이스 추가`를 누릅니다.
5. Marketplace 목록에서 Rubricodex를 찾아 설치합니다.
6. 새 Codex 작업에서 `@Rubricodex`를 멘션하거나, “Rubricodex로 이 요청을 bounded goal로 정리해줘”처럼 요청합니다.

CLI로 Marketplace만 추가하고 싶다면 같은 설정을 아래처럼 넣을 수 있습니다.

```bash
codex plugin marketplace add jaehoonE7877/rubricodex \
  --ref main \
  --sparse .agents/plugins \
  --sparse plugins/rubricodex
```

> [!NOTE]
> 위 명령은 Codex가 Rubricodex 플러그인을 찾을 수 있게 Marketplace를 등록합니다.
> 터미널에서 `rubricodex` 명령을 실행하는 Python CLI 설치는 다음 섹션을 따로 진행하세요.

## 로컬 CLI 설치

로컬에서 artifact를 만들고 검증 명령을 직접 실행하려면 Python CLI를 설치합니다.

```bash
git clone https://github.com/jaehoonE7877/rubricodex.git
cd rubricodex
python3 -m pip install -e .
rubricodex --help
```

설치하지 않고 repo 안에서 바로 실행할 수도 있습니다.

```bash
python3 -m rubricodex.cli --help
```

## 빠른 시작

가장 짧은 흐름은 `init`으로 작업 폴더를 준비하고, 자연어 목표를 `plan draft`로 압축하는 것입니다.

```bash
rubricodex init
rubricodex plan draft \
  --run-id example-v1.0 \
  --goal "관리자 dashboard page를 만들고 test evidence를 남겨줘."
```

설치하지 않은 상태라면 같은 명령을 Python module로 실행합니다.

```bash
python3 -m rubricodex.cli init
python3 -m rubricodex.cli plan draft \
  --run-id example-v1.0 \
  --goal "관리자 dashboard page를 만들고 test evidence를 남겨줘."
```

## 어떻게 돌아가나

```mermaid
flowchart LR
  A["@Rubricodex goal"] --> B["Intent brief"]
  B --> C["Evaluation matrix"]
  C --> D["Taskpack goal.md"]
  D --> E["Codex implementation"]
  E --> F["Evidence"]
  F --> G["Scorecard + Report"]
  G --> H["Retune goal if needed"]
```

쉽게 말하면, Rubricodex는 Codex에게 바로 “구현해줘”라고 던지지 않습니다.

| 단계 | 하는 일 | 결과물 |
| --- | --- | --- |
| 1 | 요청을 작고 명확한 목표로 정리 | `brief.json` |
| 2 | 성공 기준을 표로 고정 | `evaluation-matrix.json` |
| 3 | Codex가 실행할 목표 파일 생성 | `goal.md` |
| 4 | 구현 후 검증 근거 정리 | `evidence.json` |
| 5 | 점수와 리포트 생성 | `scorecard.json`, `report.md` |
| 6 | 부족하면 다시 시도할 지시 생성 | `retune_goal.md` |

## 모드 선택

| Mode | 언제 쓰나 | 예시 |
| --- | --- | --- |
| `micro` | 아주 작은 수정 | 오타, 문구 변경 |
| `quick` | 작고 되돌리기 쉬운 작업 | 작은 버그 수정 |
| `standard` | 일반적인 제품 개발 | endpoint, 화면, 테스트 추가 |
| `strict` | 실수 비용이 큰 작업 | 결제, 권한, 개인정보, migration |
| `audit` | 구현 없이 검토만 할 때 | 현재 diff나 결과 리뷰 |

## 예시

Fixture는 app-first/local CLI 흐름이 한 번에 어떻게 이어지는지 보여줍니다.

[examples/source-code-endpoint](examples/source-code-endpoint)

```bash
python3 -m rubricodex.cli --root examples/source-code-endpoint goal compile --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint prompt lint --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint matrix lock --run-id example-v0.1
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate run --run-id example-v0.1 --parallel 2
python3 -m rubricodex.cli --root examples/source-code-endpoint orchestrate status --run-id example-v0.1
```

<details>
<summary>낮은 단계 명령 보기</summary>

```bash
rubricodex goal compile --run-id example-v0.1
rubricodex prompt lint --run-id example-v0.1
rubricodex matrix lock --run-id example-v0.1
rubricodex run local --run-id example-v0.1
rubricodex probe plan --run-id example-v0.1
rubricodex probe run --run-id example-v0.1 --parallel 2
rubricodex score compute --run-id example-v0.1
rubricodex report --run-id example-v0.1
```

</details>

## Codex app plugin 표면

Codex app plugin 파일은 [plugins/rubricodex](plugins/rubricodex)에 있습니다.

App-first 흐름은 아래 명령으로 같은 artifact를 검증합니다.

```bash
rubricodex app session import --from .rubricodex/app/sessions/<session-id>/app-session.json
rubricodex app collect --run-id example-v0.1
rubricodex orchestrate run --run-id example-v0.1
rubricodex orchestrate status --run-id example-v0.1
```

로컬 runner는 기본적으로 dry-run handoff만 기록합니다. 직접 Codex CLI 실행은 `--execute`를 명시할 때만 시도합니다.

## Product SSoT

제품 기준, roadmap, schema, CLI command, artifact 계약은 Notion에서 관리합니다.

- Notion Canonical SSoT: https://app.notion.com/p/3544408817af8182b23ecf3ba169d82e

이 repo에는 별도 SSoT mirror를 두지 않습니다. README는 짧은 입구이고, 상세 제품 기준은 Notion을 기준으로 합니다.
