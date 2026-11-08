# Security Policy

## Reporting a Vulnerability

If you discover a potential security issue in Synapse Harness, please do not disclose it publicly in an open GitHub issue.

Instead, please send an advisory email directly to:
- **Contact**: `lainholic@users.noreply.github.com`

Please include:
1. A clear description of the vulnerability.
2. Steps or a minimal proof-of-concept to reproduce the behavior.
3. Potential impact and suggested mitigations.

We will review reports promptly and collaborate with you on a responsible fix and release timeline.

## Data Boundary Policy

Synapse Harness Stage 1 runs entirely locally on your machine and never transmits code, logs, or credentials over the network.

When utilizing Stage 2 with external AI models or subagents, be mindful of your organizational security boundaries, as code snippets may be routed through third-party model APIs depending on your agent runtime configuration.
