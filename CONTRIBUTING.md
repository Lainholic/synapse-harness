# Contributing to Synapse Harness

Thank you for your interest in improving Synapse Harness.

## Code of Conduct

Please be respectful, constructive, and grounded in engineering facts when interacting with this repository.

## How to Contribute

1. **Open an Issue First**:
   - For bug reports or feature suggestions, open an issue describing the problem, reproduction steps, Python version, and operating system.
2. **Fork and Create a Branch**:
   - Create a feature branch from `main`:
     ```bash
     git checkout -b feature/my-feature
     ```
3. **Run Tests**:
   - Ensure all unit tests pass locally before submitting:
     ```bash
     python tests/test_harness.py
     ```
4. **Documentation Synchronization**:
   - Synapse Harness maintains bilingual documentation. If you modify `README.md`, please update `README.ko.md` accordingly (and vice-versa).
5. **Submit a Pull Request**:
   - Open a PR against the `main` branch with a clear description of the change and verification evidence.

## Coding Standards

- Code must run on Python 3.10, 3.11, and 3.12 across Windows, Linux, and macOS.
- Keep dependencies minimal. Standard library modules should be prioritized whenever possible.
- Ensure `sys.dont_write_bytecode = True` is preserved in CLI tools to avoid polluting target workspaces.
