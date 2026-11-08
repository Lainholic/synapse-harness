# Synapse Harness (시냅스 하네스)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![Compatible](https://img.shields.io/badge/Compatible-Claude%20Code%20%7C%20Cursor%20%7C%20Codex%20%7C%20Antigravity-orange.svg)](#)

[English](README.md) | [한국어](README.ko.md)

**Synapse Harness(시냅스 하네스)**는 단일 AI의 **'자기 긍정 편향(Self-confirmation bias)'**과 **'상관 오류(Correlated Error)'**를 기계적으로 분쇄하기 위해 설계된 실전형 적대적 교차 검증 스킬입니다.

프롬프트 수준의 가상 좌뇌/우뇌 역할극에 의존하지 않고, **초고속 로컬 기계 린터(AST 바이트 격리 컴파일 및 구형 모델명 소독)**와 **외부 이기종 AI의 적대적 비판(악마의 변호인, Red-Team)**을 결합한 3단계 하이브리드 검증 파이프라인을 집행합니다.

---

## ⚡ 문제의식: AI 코딩의 자기 긍정 편향

단일 AI 모델이 자신이 작성한 코드를 스스로 검토할 때 필연적인 한계가 발생합니다:
1. 자신이 놓친 엣지케이스, 경계 조건, 리소스 누수를 똑같이 보지 못합니다.
2. 결함을 지적받아도 그럴듯한 사후합리화 변명으로 코드를 정당화하려 듭니다.
3. 동일 모델 내에서 가상 검토자 역할을 시켜도, 동일한 확률 분포를 공유하므로 오류를 그대로 승인(Rubber-stamping)하는 경향이 있습니다.

---

## 🛡️ 3단계 하이브리드 검증 파이프라인

```
[검증 대상 코드]
     │
     ▼
┌───────────────────────────────────────────────┐
│  Step 1: 기계적 팩트 체크 (지연시간 0초)      │
│  - 임시 격리 디렉터리에서 Python AST 컴파일  │
│  - 작업 폴더 내 __pycache__ / .pyc 오염 0개   │
│  - ruff 정적 린터 연동 검사                   │
│  - 구형 LLM 모델명 날조 탐지 및 소독          │
└──────────────────────┬────────────────────────┘
                       │ PASS
                       ▼
┌───────────────────────────────────────────────┐
│  Step 2: 적대적 Red-Team 비판 (외부 AI/워커)  │
│  - 악마의 변호인(Devil's Advocate) 페르소나   │
│  - 공격 축: 메모리 누수, 동시성 경합,         │
│    미처리 예외, 리소스 고갈                   │
│  - 어설픈 칭찬 금지, 약점 위주 냉정 타격      │
└──────────────────────┬────────────────────────┘
                       │ 비판 전달
                       ▼
┌───────────────────────────────────────────────┐
│  Step 3: 최종 Judge 판정 및 종합              │
│  - 사용자 원래 지시 vs 기계 팩트 vs 비판 대조 │
│  - 근거 없는 억지 비판 기각, 실질 결함 수용   │
│  - 검수와 수정의 엄격한 분리 원칙 고수        │
└───────────────────────────────────────────────┘
```

---

## 🚀 1분 퀵스타트

### 설치 방법

사용 중인 에이전트의 스킬 디렉터리에 클론하기만 하면 즉시 인식됩니다:

**Codex / Antigravity 환경:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.agents/skills/synapse-harness
```

**Claude Code 환경:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.claude/skills/synapse-harness
```

**Cursor 환경 (프로젝트 루트):**
```bash
git clone https://github.com/Lainholic/synapse-harness.git .cursor/skills/synapse-harness
```

---

## 💻 사용 예시

설치 후 에이전트에게 자연어로 지시합니다:

```text
"src/auth/token_verifier.py 파일에 시냅스 하네스 돌려줘"
```
```text
"PR 머지하기 전에 하네스로 적대적 검증해봐"
```
```text
"상태 머신 전이 로직에 하네스 걸어서 엣지케이스 털어봐"
```

### 터미널 CLI 직접 실행

에이전트 없이 터미널에서 기계 린터를 단독 실행할 수도 있습니다:

```bash
# 구문 문법, 인코딩, 모델명 무결성 즉시 검사
python scripts/verify.py path/to/your/file.py

# 구형 모델명 찌꺼기 검색 및 최신 세대 자동 치환
python scripts/model_sanitizer.py path/to/project/ --fix
```

---

## 📁 디렉터리 구조

```
synapse-harness/
├── SKILL.md                  # 에이전트 스킬 명세 및 실행 계약
├── LICENSE                   # MIT 라이선스
├── README.md                 # 영문 공식 문서
├── README.ko.md              # 한글 공식 문서
└── scripts/
    ├── verify.py             # 격리 AST 컴파일러 및 정적 린터
    └── model_sanitizer.py    # LLM 모델명 소독기 및 자동 치환기
```

---

## 📜 3대 운영 원칙

1. **검수와 수정의 엄격한 분리**: 검수 요청은 오직 읽기·검사만 허용합니다. 사용자의 명시적인 수정 승인 없이 코드를 임의로 고치지 않습니다.
2. **선 증거 후 판정**: 모든 지적은 구체적인 파일:라인, 실패 트리거, 실체적 근거를 제시해야 합니다.
3. **작업 환경 무오염**: 기계 검사는 휘발성 메모리/임시 디렉터리에서 수행되어 개발자의 작업 공간에 `.pyc`나 `__pycache__` 찌꺼기를 남기지 않습니다.

---

## 📄 라이선스

[MIT License](LICENSE)에 따라 배포됩니다. Copyright (c) 2026 Lainholic.
