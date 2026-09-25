# Cupel Platform Adapters

An adapter carries the canonical organisation onto one platform's mechanisms. It maps the six face classes onto the platform's permission model, names the platform's entry point, and states honestly which capabilities the platform has. It never adds a unit, changes a card, or restates the law.

Phase 1 ships three carriers. Every other platform is served by the portable carrier until a dedicated adapter exists (`orgs/cupel/docs/extension-guide.md`).

| Carrier | Directory | Primary for | Mechanism |
|---|---|---|---|
| Claude Code | `claude/` | Claude Code CLI and IDE sessions in this repository | `.claude/agents/cupel/` cards (byte-identical mirror of `orgs/cupel/agents/`), pointer block in `CLAUDE.md`, entry `claude --agent cupel-case-marshal` |
| Codex and other `AGENTS.md` readers | `codex/` | OpenAI Codex CLI/cloud, and any agent that loads `AGENTS.md` | Cupel routing section in `AGENTS.md` plus `portable/prompt-protocol.md` (sequential emulation) |
| Portable | `portable/` | Claude Projects, ChatGPT Projects, any chat surface, any LLM with no agent mechanism | `chat-kernel.md` as system or project instructions, `knowledge-bundle/` as uploaded knowledge, `prompt-protocol.md` as the request grammar |

## Adapter contract

Each adapter document states these fields, in this order, using the labels **CONFIRMED** (verified in this repository or in the session that wrote the adapter), **REPORTED** (observed in the accepted design's fresh-process runs of 2026-09-25, whose artifacts were not preserved), or **UNVERIFIED** (not checked; do not rely on it):

```yaml
platform:
supported_surfaces:
instruction_mechanism:
repository_context:
agent_mechanism:
delegation_mechanism:
parallelism:
tool_execution:
persistent_context:
limitations:
capability_mapping:      # CAP_* -> yes / no / unknown, with label
fallback_strategy:
invocation_examples:
schema_version_targeted: "1.0"
```

## Canonical capability names

Adapters map platform features onto these names and nothing else:

```text
CAP_REPO_READ  CAP_REPO_WRITE  CAP_FILE_EDIT  CAP_TERMINAL  CAP_COMMAND_EXECUTION
CAP_PARALLEL_AGENT  CAP_NATIVE_SUBAGENT  CAP_BACKGROUND_AGENT  CAP_WEB_SEARCH  CAP_MCP
CAP_GITHUB  CAP_SIMULATOR  CAP_FORMAL_TOOL  CAP_COVERAGE_TOOL
CAP_PERSISTENT_INSTRUCTIONS  CAP_PROJECT_CONTEXT  CAP_TOOL_RESULT_CAPTURE
```

`CAP_SIMULATOR`, `CAP_FORMAL_TOOL`, and `CAP_COVERAGE_TOOL` are properties of the project's `.soc-dv/config.json` and the machine the agent runs on, not of the AI platform; every adapter marks them `depends on project configuration`.

## Phase 1 capability summary

| Capability | Claude Code | Codex / AGENTS.md readers | Portable (Projects, chat) |
|---|---|---|---|
| CAP_REPO_READ | yes (CONFIRMED) | yes for Codex CLI (UNVERIFIED in this rebuild); depends on the reader | no; material is pasted or uploaded |
| CAP_REPO_WRITE / CAP_FILE_EDIT | yes, drafting faces only under elevation (CONFIRMED tool envelope) | depends on sandbox mode (UNVERIFIED) | no |
| CAP_TERMINAL / CAP_COMMAND_EXECUTION | runner and stewardship faces only (CONFIRMED envelope) | depends on approval policy (UNVERIFIED) | no |
| CAP_NATIVE_SUBAGENT | yes, `.claude/agents/` (CONFIRMED mechanism; nested discovery REPORTED) | Codex native agents UNVERIFIED (Phase 2); emulated | no; emulated |
| CAP_PARALLEL_AGENT | yes, several Agent calls in one turn (REPORTED in T2) | UNVERIFIED; sequential emulation | no; sequential emulation |
| CAP_BACKGROUND_AGENT | UNVERIFIED; not used by Cupel | UNVERIFIED; not used | no |
| CAP_PERSISTENT_INSTRUCTIONS | `CLAUDE.md` (CONFIRMED) | `AGENTS.md` (CONFIRMED for Codex by repository convention) | project or system instructions (CONFIRMED for Claude Projects; ChatGPT Projects UNVERIFIED in this rebuild) |
| CAP_PROJECT_CONTEXT | repository checkout (CONFIRMED) | repository checkout (Codex) | uploaded knowledge bundle |
| CAP_TOOL_RESULT_CAPTURE | raw stdout quoted by the runner (CONFIRMED path) | depends on execution (UNVERIFIED) | pasted raw output only |
| CAP_MCP, CAP_WEB_SEARCH, CAP_GITHUB | not used by Cupel Phase 1 | not used | not used |

Where a capability is absent, the organisation does not shrink: the missing mechanism is emulated by the prompt protocol, and anything that would have needed real execution stays Unverified and the verdict stays NOT READY. That is the intended behaviour, not a degraded mode.

## Deferred adapters (Phase 2, all UNVERIFIED)

GitHub Copilot and VS Code (`.github/copilot-instructions.md`, custom agents, prompt files), Cursor (`.cursor/rules/`, subagents), xAI Grok, Moonshot Kimi, NVIDIA Nemotron and other open-model or API-orchestrated environments, native Codex or ChatGPT agents, and cloud runners. Each will be written only after verification against that vendor's current official documentation, as the repository's policy requires. Until then, all of them use the portable carrier.
