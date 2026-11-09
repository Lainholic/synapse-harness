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

Output is emitted in structured JSON (example snippet):
```json
{
  "success": true,
  "report": {
    "file": "/path/to/target_file.py",
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
      "ruff 정적 린터 PASS",
      "구형 모델명 기계 검사 PASS (0개 확인)"
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

1. **Python-Centric Static Analysis & Format Boundaries**:
   - Comprehensive AST compilation (`py_compile`) and linter checks (`ruff`) are currently fully implemented for **Python only**.
   - `.json` files strictly enforce RFC 8259 syntax (rejecting non-standard constants such as `NaN` and `Infinity`) with `syntax_pass: true`.
   - Other text/markdown/code formats (`.md`, `.js`, `.ts`, `.html`) are verified for UTF-8 integrity (`encoding_pass: true`), while `syntax_pass` is explicitly reported as `null` (`not_checked`) to avoid falsely claiming AST language validation when language-specific parsers are not executed.
2. **Static Syntax vs. Explicit Runtime Verification**:
   - By default, `verify.py` performs static analysis without importing target modules or executing tests (note that external analyzers like ruff and mypy execute as host processes under user privileges).
   - When explicitly opted-in via `--test`, paired unit tests are executed under strict path isolation. For `pytest`, structured JUnit XML output is strictly parsed with testcase-to-counter consistency checks, disallowing unvalidated text fallbacks on missing XML. Results must contain at least one pure passing test case (all-skipped or only-xfail runs are rejected). Path prioritization places the target directory ahead of the test runner directory; however, Python retains already-cached modules in `sys.modules` (e.g. if the target shadows a standard library name like `os.py`), which path ordering alone does not override. Additionally, XML validation inspects format and counter consistency and does not sandbox hostile test processes from emitting crafted reports if given arbitrary code execution privileges.
   - When explicitly opted-in via `--smoke`, the module is loaded under isolated standalone execution with promoted directory pathing; package-relative imports (`from .sibling import ...`) require a full package anchor and are not supported in smoke mode. For package-relative testing, configure appropriate package contexts (e.g. installed package or root PYTHONPATH) and run via `--test`; `--test` does not automatically reconstruct package anchors.
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
