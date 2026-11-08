# Synapse Harness (시냅스 하네스)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![Compatible](https://img.shields.io/badge/Compatible-Claude%20Code%20%7C%20Cursor%20%7C%20Codex%20%7C%20Antigravity-orange.svg)](#)

[English](README.md) | [한국어](README.ko.md)

**Synapse Harness** is a production-grade adversarial cross-verification skill designed to eliminate **AI self-confirmation bias** and **correlated errors**.

Instead of relying on prompt-only roleplay, Synapse Harness unifies **zero-overhead mechanical static linting** (AST compilation & legacy model hallucination sanitization) with **adversarial Red-Team AI audits (Devil's Advocate)** into a strict 3-stage validation pipeline.

---

## ⚡ The Problem: Self-Confirmation Bias in AI Coding

When an AI model reviews its own generated code, it inherently suffers from **self-confirmation bias**:
1. It overlooks its own blind spots, missing edge cases, and boundary violations.
2. It generates plausible-sounding explanations ("post-hoc rationalization") to defend incorrect code.
3. Prompt-only "virtual reviewer" tricks (asking the same model to pretend to be a reviewer) often rubber-stamp flaws because they share the same underlying token distribution.

---

## 🛡️ The 3-Stage Hybrid Pipeline

```
[Target Code]
     │
     ▼
┌───────────────────────────────────────────────┐
│  Step 1: Mechanical Fact Check (0s latency)   │
│  - Python AST byte-compile in isolated tmpdir │
│  - Zero __pycache__ / .pyc workspace pollution│
│  - Ruff static analysis integration           │
│  - Legacy LLM hallucination sanitizer         │
└──────────────────────┬────────────────────────┘
                       │ PASS
                       ▼
┌───────────────────────────────────────────────┐
│  Step 2: Adversarial Red-Team Audit (External)│
│  - Devil's Advocate persona                   │
│  - Attack surface: memory leaks, race conds,  │
│    unhandled edge cases, resource exhaustion  │
│  - No compliments; flaws-only critique        │
└──────────────────────┬────────────────────────┘
                       │ Critique
                       ▼
┌───────────────────────────────────────────────┐
│  Step 3: Final Judge & Synthesis              │
│  - Cross-examine user intent vs facts vs audit│
│  - Dismiss ungrounded or speculative attacks  │
│  - Strict separation of audit vs code editing │
└───────────────────────────────────────────────┘
```

---

## 🚀 1-Minute Quick Start

### Installation

Drop the repository into your preferred AI agent skill directory:

**For Codex / Antigravity:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.agents/skills/synapse-harness
```

**For Claude Code:**
```bash
git clone https://github.com/Lainholic/synapse-harness.git ~/.claude/skills/synapse-harness
```

**For Cursor (project scope):**
```bash
git clone https://github.com/Lainholic/synapse-harness.git .cursor/skills/synapse-harness
```

---

## 💻 Usage

Once installed, simply prompt your AI agent:

```text
"Run synapse-harness on src/auth/token_verifier.py"
```
```text
"Harness audit this pull request before merging"
```
```text
"Use synapse-harness to stress-test our state machine transitions"
```

### Standalone CLI Verification

You can also run the mechanical linter directly from your command line:

```bash
# Verify syntax, encoding, and model naming integrity
python scripts/verify.py path/to/your/file.py

# Scan and sanitize outdated model hallucination strings
python scripts/model_sanitizer.py path/to/project/ --fix
```

---

## 📁 Repository Structure

```
synapse-harness/
├── SKILL.md                  # Agent skill definition and execution contract
├── LICENSE                   # MIT License
├── README.md                 # English documentation
├── README.ko.md              # Korean documentation
└── scripts/
    ├── verify.py             # Mechanical AST isolated compiler & linter
    └── model_sanitizer.py    # LLM hallucination sanitizer & auto-fixer
```

---

## 📜 Operating Rules

1. **Strict Separation of Audit vs Modification**: An audit request authorizes inspection only. The agent never silently modifies code unless explicitly instructed to apply approved fixes.
2. **Evidence Before Assertions**: Every critique must cite concrete triggers, line numbers, or reproducible failure modes.
3. **Zero Workspace Contamination**: Mechanical verification runs in ephemeral memory/tempfs to ensure zero `.pyc` or `__pycache__` artifacts are left behind.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Copyright (c) 2026 Lainholic.
