# Synapse Harness

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)

[English](README.md) | [한국어](README.ko.md)

**Synapse Harness** is an AI agent skill that combines local deterministic checks with optional adversarial cross-verification.

When AI models review code they wrote themselves, they often share the same blind spots and generate convincing justifications for incorrect implementations. Synapse Harness addresses this by running local syntax and lint checks first, followed by an optional adversarial critique from a separate reviewer persona or model when requested by the user.

A successful check does not guarantee that code is completely defect-free. External reviews may send code snippets or logs to external model APIs; review the scope and target before invoking external workers.

---

## 🛡️ Architecture: 3-Stage Verification Pipeline

```
[Target Code]
     │
     ▼
┌──────────────────────────────────────────────┐
│  Stage 1: Local Deterministic Check          │
│  - Default: Pure static analysis (no smoke   │
│    import or test execution by default)      │
│  - Python compilation via isolated temp dir  │
│  - Bytecode suppression (no harness __pycache__) │
│  - Ruff static analysis (enforcing --no-fix) │
│  - Mypy static type verification (if avail)  │
│  - Configured model-name string verification │
│  - Opt-in --smoke: Isolated import check     │
│  - Opt-in --test: Paired test execution      │
└──────────────────────┬───────────────────────┘
                       │ PASS
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 2: Adversarial Audit (Optional)       │
│  - Devil's Advocate reviewer persona         │
│  - Evaluates race conditions, leaks, edge    │
│    cases, and resource boundaries            │
│  - Single-pass only upon explicit request    │
└──────────────────────┬───────────────────────┘
                       │ Findings
                       ▼
┌──────────────────────────────────────────────┐
│  Stage 3: Evidence-Grounded Synthesis        │
│  - Compares original intent, compiler logs,   │
│    and adversarial critique findings         │
│  - Dismisses speculative or invalid claims   │
│  - Produces structured review report         │
└──────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Installation

Clone the repository into your agent's skill directory:

**For Codex / Antigravity / Shared Agents:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.agents/skills/synapse-harness
```

**For Claude Code:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.claude/skills/synapse-harness
```

**For Cursor (Workspace scope):**
```bash
git clone https://github.com/Lainholic/synapse-harness.git .cursor/skills/synapse-harness
```

---

## 💻 CLI Usage

You can also run the deterministic verification tools directly from your terminal:

### 1. Verify a File
Run syntax, encoding, and lint checks against a target file:

```bash
# Navigate to the synapse-harness directory
cd path/to/synapse-harness

# Default: Static analysis (Syntax, lint, and type check without importing or executing target module)
python scripts/verify.py "/path/to/target_file.py"

# Opt-in: Strict mode (fails if external linters like ruff/mypy are not installed)
python scripts/verify.py "/path/to/target_file.py" --strict

# Opt-in: Runtime smoke-test (verifies clean module import without initialization crashes)
python scripts/verify.py "/path/to/target_file.py" --smoke

# Opt-in: Unit test execution (discovers and runs paired test_<name>.py; fails if no test is found)
python scripts/verify.py "/path/to/target_file.py" --test
```

> **Security Notice on Execution Boundaries:**  
> By default, the verifier does not smoke-import the target or run its tests. External analyzers, their configuration and plugins, and the execution environment remain separate trust boundaries. Both `--test` and `--smoke` execute code with the current user's privileges; subprocesses and timeouts are helpful isolation barriers, but they are not security sandboxes. The harness suppresses its own bytecode and uses isolated temporary directories for compilation; external tools and test runners manage their own caches per their respective configurations. Use appropriate container or VM isolation when analyzing untrusted third-party code.

Output is emitted in structured JSON:
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

### 2. Check Legacy Model Strings (Read-Only)
Check whether a file or directory contains outdated LLM model strings:

```bash
python scripts/model_sanitizer.py "/path/to/project_dir"
```

> **Warning on Auto-Fix:**
> Running `python scripts/model_sanitizer.py "/path/to/project_dir" --fix` modifies files directly on disk. Only use `--fix` after taking backups or verifying version control status.

---

## ⚠️ Known Limitations & Boundaries

We believe in engineering transparency. Please review the following limitations before relying on Synapse Harness in your workflows:

1. **Python 중심 정적 분석 및 언어별 검증 경계**:
   - AST 격리 컴파일(`py_compile`) 및 린터 검사(`ruff`)는 현재 **Python에 완전하게 구현**되어 있습니다.
   - `.json` 파일은 비표준 상수(`NaN`, `Infinity`)를 거부하는 엄격한 RFC 8259 규격을 적용하여 `syntax_pass: true`로 판정합니다.
   - 기타 텍스트/마크다운/코드(`.md`, `.js`, `.ts`, `.html`)는 UTF-8 무결성(`encoding_pass: true`)을 검증하며, 언어 전용 AST 구문 분석기가 미실행되었음을 명확히 알리기 위해 `syntax_pass`는 `null`(`not_checked`)로 제공됩니다.
2. **정적 분석 vs. 명시적 런타임 검증 경계**:
   - 기본적으로 `verify.py`는 모듈 임포트나 테스트 코드 실행 없이 정적 분석만 수행합니다. (외부 도구인 ruff, mypy는 사용자 권한 호스트 프로세스로 실행됩니다.)
   - 사용자가 명시적으로 `--test`를 지정한 경우, `pytest` 실행 시 구조화된 JUnit XML(`--junitxml`)을 필수로 파싱하여 터미널 텍스트 위장을 차단하며, XML 누락 시 텍스트 파서로의 폴백을 엄격히 금지합니다. 또한 전체 건너뛰기(all skipped)나 xfail/expected failures만 있는 경우는 실패로 처리하고 **최소 1개 이상의 순수 성공 테스트**가 확인되어야 PASS로 판정합니다.
3. **Agent-Mediated Stages 2 & 3**:
   - Stage 1 runs autonomously as a standalone CLI tool.
   - Stages 2 and 3 require an agent environment (such as Antigravity, Claude, or custom LLM runners) interpreting `SKILL.md` to trigger adversarial reviews.
4. **Context-Insensitive Model String Matching**:
   - `model_sanitizer.py` matches strings by pattern. It does not differentiate between actual LLM configuration calls and historical citations or test fixture data.
5. **Data Boundary & External API Consideration**:
   - When Stage 2 is executed via third-party AI models, code snippets and logs may be transmitted over the network. Always verify organizational compliance before using external workers on proprietary codebases.

---

## 🗺️ Roadmap

- [ ] Add ESLint and TypeScript compiler (`tsc`) passes for JavaScript and TypeScript files.
- [ ] Add unified standalone CLI command (`python -m synapse_harness run <target>`) with pluggable LLM backends.
- [ ] Support custom AST lint rules and ignore pragmas.
- [ ] Add pre-commit git hook configuration.

---

## 🤝 Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on code style, tests, and documentation synchronization.

---

## 🔒 Security

For vulnerability disclosures and security policies, please see [SECURITY.md](SECURITY.md).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
