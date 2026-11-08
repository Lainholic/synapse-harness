# Synapse Harness (시냅스 하네스)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)

[English](README.md) | [한국어](README.ko.md)

**Synapse Harness**는 로컬 기계 검사와 선택적인 적대적 AI 보조 검토를 결합하는 AI 에이전트 검증 스킬입니다.

AI 모델이 자신이 직접 작성한 코드를 스스로 검토할 때, 동일한 사각지대를 공유하여 버그를 놓치거나 잘못된 구현을 그럴듯하게 정당화하는 '자기 긍정 편향'이 발생하기 쉽습니다. Synapse Harness는 로컬 구문 검사와 정적 린트를 먼저 실행하여 기초 결함을 기계적으로 걸러내고, 사용자가 요청했을 때 별도의 페르소나나 외부 모델을 통해 비판적 검토를 수행하도록 지원합니다.

검사가 통과했다고 해서 코드에 결함이 없음을 보장하지는 않습니다. 외부 검토 진행 시 선택된 코드나 로그가 타사 모델 API로 전송될 수 있으므로, 사용 전 검토 대상과 범위를 확인하십시오.

---

## 🛡️ 아키텍처: 3단계 검증 파이프라인

```
[검증 대상 코드]
       │
       ▼
┌──────────────────────────────────────────────┐
│  1단계: 로컬 기계 검사 (로컬 즉시 실행)      │
│  - 기본 모드: 스모크/테스트 비실행 정적 검사 │
│  - 임시 디렉터리 기반 Python 격리 컴파일     │
│  - 바이트코드 억제 (__pycache__ 잔여 방지)   │
│  - Ruff 정적 분석 (--no-fix 옵션 강제)       │
│  - Mypy 정적 타입 검사 연동 (설치 시)        │
│  - 설정된 구형 모델명 문자열 검사            │
│  - 명시적 --smoke: 스모크 임포트 실행 검증   │
│  - 명시적 --test: 대응 단위 테스트 격리 실행 │
└──────────────────────┬───────────────────────┘
                       │ PASS
                       ▼
┌──────────────────────────────────────────────┐
│  2단계: 적대적 교차 검토 (사용자 요청 시)    │
│  - 악마의 변호인 (Devil's Advocate) 관점     │
│  - 동시성 경합, 메모리 누수, 경계 조건 검토 │
│  - 사용자의 명시적 지시가 있을 때만 호출     │
└──────────────────────┬───────────────────────┘
                       │ 비판 수집
                       ▼
┌──────────────────────────────────────────────┐
│  3단계: 근거 기반 종합 판정 및 보고         │
│  - 원래 의도, 컴파일러 로그, 2단계 비판 대조 │
│  - 근거가 부족하거나 부적절한 지적은 기각    │
│  - 정형화된 검토 보고서 출력                 │
└──────────────────────────────────────────────┘
```

---

## 🚀 빠른 시작 (Quick Start)

### 설치 방법

사용 중인 에이전트의 스킬 디렉터리에 본 저장소를 클론합니다:

**Codex / Antigravity / 공용 에이전트:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.agents/skills/synapse-harness
```

**Claude Code:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.claude/skills/synapse-harness
```

**Cursor (프로젝트 단위):**
```bash
git clone https://github.com/Lainholic/synapse-harness.git .cursor/skills/synapse-harness
```

---

## 💻 CLI 직접 사용법

터미널에서 기계 검사 도구를 직접 실행할 수도 있습니다:

### 1. 단일 파일 검증
대상 파일의 구문, 인코딩, 정적 린터를 검사합니다:

```bash
# synapse-harness 저장소 디렉터리로 이동
cd path/to/synapse-harness

# 기본 검증: 안전한 정적 분석 (구문 및 린터 검사, 코드 실행 없음)
python scripts/verify.py "/path/to/target_file.py"

# 선택적 실행: 스모크 임포트 검증 (모듈 초기화 런타임 크래시 여부 검출)
python scripts/verify.py "/path/to/target_file.py" --smoke

# 선택적 실행: 단위 테스트 실행 (대응하는 test_<name>.py 격리 실행)
python scripts/verify.py "/path/to/target_file.py" --test
```

> **실행 경계 및 보안 주의사항:**  
> 기본 모드는 대상 파일의 스모크 임포트와 단위 테스트를 실행하지 않습니다. 다만 외부 분석기, 프로젝트 설정, 플러그인 및 실행 환경은 별도의 신뢰 경계입니다. `--test` 및 `--smoke`는 현재 사용자 권한으로 코드를 직접 실행하므로, 신뢰할 수 없는 외부 코드는 컨테이너나 격리된 VM 환경에서 분석하십시오.

출력 결과는 구조화된 JSON 형태로 제공됩니다:
```json
{
  "success": true,
  "report": {
    "file": "/path/to/target_file.py",
    "extension": ".py",
    "encoding_pass": true,
    "syntax_pass": true,
    "linter_status": "pass",
    "details": [
      "py_compile 구문 검사 PASS (오염 없는 격리 컴파일)",
      "ruff 정적 린터 PASS (코드 무결)"
    ]
  }
}
```

### 2. 구형 모델명 문자열 검사 (읽기 전용)
파일이나 프로젝트 디렉터리 내에 구버전 LLM 모델명 문자열이 존재하는지 검사합니다:

```bash
python scripts/model_sanitizer.py "/path/to/project_dir"
```

> **자동 치환(--fix) 사용 시 주의사항:**  
> `python scripts/model_sanitizer.py "/path/to/project_dir" --fix`를 실행하면 파일이 디스크에서 직접 수정됩니다. 버전 관리 상태를 확인하거나 백업을 수행한 후 사용하십시오.

---

## ⚠️ 한계 및 지원 범위 (Known Limitations)

공학적 투명성을 위해 현재 구현의 한계와 경계를 명확히 안내합니다:

1. **파이썬 중심의 정적 분석**:
   - 정밀 AST 컴파일(`py_compile`)과 정적 린터(`ruff`)는 현재 **Python 파일에 대해서만 완전히 지원**됩니다.
   - 기타 형식(`.json`, `.md`, `.js`, `.ts`, `.html`)은 UTF-8 인코딩 및 JSON 구문 파싱만 수행하며, ESLint나 tsc 등의 타 언어 전용 컴파일러는 1단계에 아직 내장되어 있지 않습니다.
2. **정적 구문 검사와 선택적 런타임 검증**:
   - `verify.py`는 기본 실행 시 코드를 절대 실행하지 않는 안전한 정적 분석만 수행합니다.
   - 사용자가 명시적으로 `--test` 옵션을 지정한 경우에만 대응하는 단위 테스트(`test_<name>.py`)를 `pytest` 또는 내장 `unittest`로 격리 실행합니다. 단위 테스트가 없는 파일이거나 `--test` 옵션을 생략한 경우에는 런타임 로직 결함을 정적으로 판단할 수 없으므로 테스트 코드 작성 또는 2단계 AI 검토가 필요합니다.
3. **2단계 및 3단계의 에이전트 의존성**:
   - 1단계는 독립된 파이썬 CLI로 단독 실행됩니다.
   - 2단계와 3단계는 `SKILL.md`를 해석할 수 있는 AI 에이전트 환경(Antigravity, Claude, Cursor 등) 내에서 실행됩니다.
4. **문맥을 고려하지 않는 문자열 매칭**:
   - `model_sanitizer.py`는 정규식 패턴으로 동작합니다. 따라서 과거 논문 인용, 변경 이력 문서, 테스트 픽스처 데이터 등 의도적인 과거 모델명 언급도 검출 대상에 포함될 수 있습니다.
5. **외부 AI 호출 시 데이터 경계**:
   - 2단계에서 타사 AI 모델을 활용할 경우, 코드 일부나 로그가 네트워크를 통해 전송될 수 있습니다. 비공개 또는 보안이 중요한 환경에서는 데이터 전송 정책을 사전에 확인하십시오.

---

## 🗺️ 향후 업데이트 계획 (Roadmap)

- [ ] JavaScript / TypeScript용 ESLint 및 `tsc` 정적 검사 지원 추가
- [ ] 단독 실행 가능한 CLI 통합 명령(`python -m synapse_harness run <target>`) 개발
- [ ] 사용자 정의 AST 린트 규칙 및 무시 주석(# harness:ignore) 지원
- [ ] Git Pre-commit 훅 연동 지원

---

## 🤝 기여 가이드 (Contributing)

코드 기여 및 버그 제보는 언제나 환영합니다. 코드 스타일과 문서 갱신 원칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고해 주십시오.

---

## 🔒 보안 정책 (Security)

보안 취약점 제보 정책은 [SECURITY.md](SECURITY.md)를 확인해 주십시오.

---

## 📄 라이선스 (License)

본 프로젝트는 [MIT License](LICENSE)에 따라 배포됩니다.
