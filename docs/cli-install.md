# Rubricodex CLI 설치

이 문서는 `rubricodex` Python CLI 설치만 다룹니다. 제품 기준, roadmap, schema, artifact 계약은 README의 Product SSoT 링크를 기준으로 확인합니다.

## 요구사항

- Python 3.10 이상
- Git
- Rubricodex repo checkout

Python 버전을 먼저 확인합니다.

```bash
python3 --version
```

## 새로 clone해서 설치

```bash
git clone https://github.com/jaehoonE7877/rubricodex.git
cd rubricodex
python3 -m pip install -e .
rubricodex --help
```

## 기존 checkout에서 설치

이미 repo를 받은 상태라면 해당 폴더에서 editable install만 실행합니다.

```bash
cd /path/to/rubricodex
python3 -m pip install -e .
rubricodex --help
```

## 설치 없이 실행

repo 안에서만 잠깐 확인할 때는 Python module로 바로 실행할 수 있습니다.

```bash
python3 -m rubricodex.cli --help
```

## Codex에게 설치 요청

Codex 채팅에서는 아래 프롬프트를 그대로 붙여넣으면 됩니다.

```txt
Rubricodex 로컬 CLI를 이 GitHub repo 기준으로 설치해줘.
설치 절차는 docs/cli-install.md를 확인하고, Python 3.10+인지 확인한 뒤
editable install로 설치하고 `rubricodex --help`까지 검증해줘.
```
