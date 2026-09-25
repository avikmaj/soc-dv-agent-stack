# Changelog

## Unreleased

- Add the Cupel verification organisation as an optional layer under `orgs/cupel/` (28 agent cards, 5 schemas, adapters for Claude Code, Codex/`AGENTS.md`, and portable chat surfaces, parity and consistency tools with tests), with a Claude Code mirror under `.claude/agents/cupel/` and pointer sections in `CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/architecture.md`, and `docs/harnesses.md`. No change to skills, scripts, tests, schemas, or CI. Cupel version 0.2.0; see `orgs/cupel/CHANGELOG.md` and `orgs/cupel/docs/rebuild-notes.md`.

## 0.1.0 - 2026-09-24

- Initial public foundation under active validation; not a production-readiness claim.
- See `docs/issues/stack-issue-register.md` and `docs/audits/2026-09-24/static-security-audit.md` for open findings and evidence gaps.
- Twenty canonical design/DV skills.
- Claude Code and Codex project-local adapters.
- JSON schemas for verification plans, traceability, regression results, and waivers.
- Safe bootstrap, adapter synchronization, repository validation, and shell-free tool runner.
- CI, tests, security policy, threat model, and evaluation framework.
