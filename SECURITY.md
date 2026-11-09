# Security Policy

## Reporting a Vulnerability

If you discover a potential security vulnerability in Synapse Harness, please do not disclose it publicly in an issue or pull request.

Please report vulnerabilities through **GitHub Private Vulnerability Reporting**:
1. Navigate to the repository's **Security** tab.
2. Under "Reporting", click **Report a vulnerability**.
3. Fill in the advisory form with:
   - A clear description of the vulnerability.
   - Steps or a minimal proof-of-concept to reproduce the behavior.
   - Potential impact and suggested mitigations.

This ensures the report remains strictly confidential until a patch is developed and released.

## Execution and Trust Boundaries

- **Static Analysis Mode (Default)**: Executes `py_compile` and, when available, local linters (`ruff`, `mypy`) under the current user's operating system privileges. The harness itself contains no telemetry and transmits no data over the network.
- **Dynamic Options (`--smoke`, `--test`)**: Invoking `--smoke` (importing the target module) or `--test` (running paired test suites) executes target code directly with your user privileges.
- **Isolation Warning**: Timeouts and subprocesses provide fault isolation, but they are not cryptographic or operating system security sandboxes. When analyzing untrusted third-party code, execute the harness within a container or isolated virtual machine with network restrictions.
