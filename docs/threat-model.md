# Threat Model

## Assets

Confidential specifications and RTL; verification IP; credentials and license settings; EDA scripts/reports; coverage and bug data; Git history; workstation and network access.

## Threats

- Prompt injection hidden in source comments, documents, logs, issues, or web content.
- Destructive or over-broad shell commands.
- Exfiltration through network tools, MCP servers, telemetry, or pasted prompts.
- Dependency or update compromise.
- Hallucinated PASS/coverage/compliance claims.
- Poisoned persistent memory and incorrect reusable “lessons.”
- Direct edits to generated/vendor collateral.
- Unsound waivers or coverage exclusions.

## Controls

- No hooks, telemetry, remote MCPs, self-update, or runtime dependencies.
- Project-local installation and explicit dry run.
- Shell-free command execution from JSON argument arrays.
- Approval gates for network, Git writes, deletion, installation, off-project paths, secrets, exclusions, and waivers.
- Evidence taxonomy and mandatory residual-gap reporting.
- SHA-pinned CI actions and adapter-drift checks.
- Secret-pattern and unsafe-pattern validation.

## Residual risk

An approved tool command can still be dangerous or leak data; models can reason incorrectly; licensed-tool configuration may expose sensitive paths; and public-model use may violate employer policy. Human review and isolated execution remain required.
