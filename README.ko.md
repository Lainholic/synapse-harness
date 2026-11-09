# Synapse Harness

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)

[English](README.md) | [한국어](README.ko.md)

**Synapse Harness**는 AI 코딩 에이전트가 생성한 파이썬 코드의 기본적인 문법 오류, 린트 누락, 인코딩 깨짐, 구형 모델명 표기를 커밋 전에 로컬에서 빠르게 점검하기 위한 경량 검증 도구입니다.

---

### 왜 만들었는가?

Cursor, Windsurf, Claude Code 등 AI 코딩 도구를 사용하다 보면, 에이전트가 "수정을 완료했고 테스트도 통과했다"고 보고하지만 실제로는 기초적인 문법 오류(`SyntaxError`)가 남아있거나, 문서나 프롬프트에 예전 2024년 구형 모델명(GPT-4o, Claude 3.5 Sonnet 등)을 관성적으로 날조해 두는 일이 자주 발생합니다.

Synapse Harness는 커밋하기 전에 터미널에서 가볍게 한 번 돌려보고 이러한 실수를 걸러낼 수 있도록 도와줍니다:
- 격리된 임시 디렉터리에서 AST 컴파일을 수행하여 문법 유효성을 확인합니다.
- 로컬 환경에 설치된 린터(ruff) 및 타입 검사기(mypy)를 비파괴 방식으로 가동합니다.
- 선택적으로 짝지어진 단위 테스트를 실행하고 JUnit XML 결과를 검증합니다.
- 파일 및 폴더 전체에서 구버전 LLM 모델명 문자열을 탐지하고 치환합니다.

---

### 주요 기능

1. **결정론적 정적 검증 (`verify.py`)**
   - 바이트코드 찌꺼기(`__pycache__`) 생성 없이 파이썬 문법 및 UTF-8 인코딩 확인
   - 환경에 설치된 경우 `ruff` 및 `mypy`를 자동으로 연동하여 잠재적 버그 스크리닝
   - CI 훅이나 에이전트 워크플로에서 파싱하기 쉽도록 구조화된 JSON 결과 출력

2. **단위 테스트 실행 (`--test`)**
   - 대상 파일과 짝지어진 테스트(`test_<name>.py`)를 pytest 또는 내장 unittest로 실행
   - XML 보고서 누락을 방지하고 실제 순수 성공(passed) 테스트가 존재하는지 확인

3. **스모크 임포트 검사 (`--smoke`)**
   - 대상 모듈을 독립 프로세스로 로드하여 상위 레벨 임포트 크래시 여부 점검

4. **구형 모델명 점검 및 정화 (`model_sanitizer.py`)**
   - 코드 및 문서에서 2024년 구형 모델명(GPT-4o, Claude 3.5 Sonnet 등) 탐지
   - `--fix` 옵션 사용 시 최신 모델 규격으로 1초 자동 치환

5. **에이전트 스킬 연동 (`SKILL.md`)**
   - 코딩 에이전트의 스킬 디렉터리에 마운트하여, 에이전트가 작업을 마쳤다고 주장하기 전에 기계적 검증을 거치도록 강제 가능

---

### 빠른 시작

#### 에이전트 스킬로 설치

사용 중인 에이전트의 스킬 디렉터리에 클론합니다:

```bash
# Codex / Antigravity / 공용 에이전트
git clone https://github.com/Lainholic/synapse-harness.git ~/.agents/skills/synapse-harness

# Claude Code
git clone https://github.com/Lainholic/synapse-harness.git ~/.claude/skills/synapse-harness

# Cursor (프로젝트 워크스페이스 범위)
git clone https://github.com/Lainholic/synapse-harness.git .cursor/skills/synapse-harness
```

#### CLI 직접 실행

터미널에서 직접 실행할 수도 있습니다:

```bash
# 1. 기본 정적 검사 (문법, 인코딩, 린터)
python scripts/verify.py path/to/file.py

# 2. 엄격 모드 (ruff나 mypy가 미설치 시 실패 처리)
python scripts/verify.py path/to/file.py --strict

# 3. 스모크 임포트 점검
python scripts/verify.py path/to/file.py --smoke

# 4. 단위 테스트 실행 및 결과 확인
python scripts/verify.py path/to/file.py --test

# 5. 구형 모델명 문자열 스캔
python scripts/model_sanitizer.py ./my_project

# 6. 구형 모델명 문자열 자동 치환
python scripts/model_sanitizer.py ./my_project --fix
```

출력 결과는 정형화된 JSON 형태로 제공됩니다:
```json
{
  "success": true,
  "report": {
    "file": "path/to/file.py",
    "extension": ".py",
    "encoding_pass": true,
    "syntax_pass": true,
    "linter_status": "pass",
    "type_check_status": "pass",
    "smoke_status": "skipped",
    "test_status": "skipped",
    "model_scan_status": "pass",
    "details": [
      "py_compile 구문 검사 PASS (격리 컴파일 완료)",
      "ruff 정적 린터 PASS"
    ]
  }
}
```

---

### 현실적인 한계 및 지원 범위

- **보안 샌드박스가 아님:** `--test` 및 `--smoke` 옵션은 현재 사용자 권한으로 파이썬 코드를 직접 실행합니다. 프로세스 분리와 타임아웃 처리가 되어 있으나 악의적인 임의 코드 실행을 가두는 보안 샌드박스는 아니므로, 신뢰할 수 없는 외부 코드는 가상머신이나 컨테이너 내부에서 실행하십시오.
- **파이썬 중심:** 문법 컴파일(`py_compile`)과 린터 연동은 파이썬 파일에 특화되어 있습니다. JSON 파일은 RFC 8259 규격을 검사하며, 그 외 마크다운이나 웹 파일은 UTF-8 인코딩 정상 여부만 점검합니다.
- **도구의 범위:** 이 도구는 문법 오류, 기본적인 린트/타입 결함, 구형 문자열 표기를 걸러내기 위한 경량 유틸리티이며, 전체 서비스의 비즈니스 통합 테스트나 완벽한 무결함을 대신하지는 않습니다.

---

### 라이선스

이 프로젝트는 [MIT License](LICENSE)에 따라 배포됩니다.
