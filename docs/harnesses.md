# Harness Support

## Claude Code

Project skills are installed to `.claude/skills/<name>/SKILL.md`; `CLAUDE.md` provides the repository contract. No hooks or MCP servers are registered. When the optional Cupel layer is present, its 28 subagents are mirrored to `.claude/agents/cupel/` and `CLAUDE.md` carries a Cupel pointer block; the entry point is `claude --agent cupel-case-marshal` (`orgs/cupel/adapters/claude/claude-code.md`).

## Codex

Project skills are installed to `.agents/skills/<name>/SKILL.md`; `AGENTS.md` provides the repository contract. No global `~/.codex` file is modified. When the optional Cupel layer is present, `AGENTS.md` carries a Cupel routing section and Cupel runs by sequential emulation of its cards (`orgs/cupel/adapters/codex/codex-repo.md`); no native Codex agents are assumed.

## Parity rule

Skill text must be byte-identical across canonical and generated locations. Run `python scripts/sync_adapters.py --check` to detect drift.

## Cupel parity rule

Cupel cards must be byte-identical between `orgs/cupel/agents/` and `.claude/agents/cupel/`. Run `python3 orgs/cupel/tools/check_parity.py` to detect drift and `--sync` to regenerate the mirror; the stack's `sync_adapters.py --check` does not cover them.
