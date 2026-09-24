# Harness Support

## Claude Code

Project skills are installed to `.claude/skills/<name>/SKILL.md`; `CLAUDE.md` provides the repository contract. No hooks or MCP servers are registered.

## Codex

Project skills are installed to `.agents/skills/<name>/SKILL.md`; `AGENTS.md` provides the repository contract. No global `~/.codex` file is modified.

## Parity rule

Skill text must be byte-identical across canonical and generated locations. Run `python scripts/sync_adapters.py --check` to detect drift.
