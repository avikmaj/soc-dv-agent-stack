# Codex and `AGENTS.md`-reader Adapter

The primary carrier for OpenAI Codex (CLI, IDE extension, cloud) and for any other coding agent that loads a repository `AGENTS.md`. Cupel's presence is announced by the routing section in `AGENTS.md` (`agents-md-section.md` is its canonical text); the organisation itself is executed by sequential emulation following `../portable/prompt-protocol.md`. No native Codex agent, skill, or multi-agent feature is required or assumed.

```yaml
platform: OpenAI Codex (CLI, IDE extension, cloud tasks) and other AGENTS.md readers
supported_surfaces: any Codex surface with the repository checked out; Codex cloud tasks on a connected repository
instruction_mechanism: AGENTS.md routing section (CONFIRMED: this repository already uses AGENTS.md as the Codex control plane); nested AGENTS.md files are not used by Cupel
repository_context: the checkout (Codex reads files; CONFIRMED by the repository's existing Codex adapter under .agents/skills/)
agent_mechanism: none assumed; native Codex custom agents or subagents are UNVERIFIED and deferred to Phase 2
delegation_mechanism: none; the Codex session plays the Marshal and each face in turn
parallelism: none assumed; sequential emulation with each card read in full before its report (UNVERIFIED whether Codex offers parallel sub-tasks; not used)
tool_execution: depends on the Codex sandbox and approval configuration chosen by the human; Cupel permits only scripts/run_tool.py entries under a verbatim approval sentence, and only in a session the human has configured to allow command execution
persistent_context: AGENTS.md (CONFIRMED); no ~/.codex changes (the repository's harness policy)
limitations:
  - one model plays every face; independence is procedural, not structural
  - the face tool envelopes cannot be enforced per face by the platform; the session-wide sandbox mode is the enforcement, and the human should choose a read-only sandbox for review-path work
  - exact flag and configuration names for Codex sandbox and approval modes are UNVERIFIED in this rebuild; consult `codex --help` and the current official documentation before relying on them
capability_mapping:
  CAP_REPO_READ: yes (CONFIRMED by repository convention)
  CAP_FILE_EDIT: depends on sandbox mode (UNVERIFIED); Cupel permits only under elevation
  CAP_COMMAND_EXECUTION: depends on approval policy (UNVERIFIED); Cupel permits only the runner shape
  CAP_NATIVE_SUBAGENT / CAP_PARALLEL_AGENT / CAP_BACKGROUND_AGENT: UNVERIFIED; not used (emulated)
  CAP_PERSISTENT_INSTRUCTIONS: yes (AGENTS.md)
  CAP_PROJECT_CONTEXT: yes (checkout)
  CAP_TOOL_RESULT_CAPTURE: yes when execution is allowed (raw stdout quoted in the runner's report)
fallback_strategy: this adapter is already the prompt-routed fallback; if AGENTS.md is not loaded by the reader, paste ../portable/chat-kernel.md as the session's instructions
invocation_examples: see below
schema_version_targeted: "1.0"
```

## Operating

Phrasing is identical to every other surface (`orgs/cupel/docs/invocation-guide.md`):

```text
Use Cupel to review rtl/axi_bridge/ and tb/axi_env/ for protocol compliance and scoreboard vacuity.
Use Cupel in Codex repo mode to give a verdict on candidate <sha>, configuration hash <hash>, tag <tag>.
Elevate Cupel/comparator-desk to implementation for tb/axi_env/axi_scoreboard.sv; I approve file edits under that path.
```

The session, acting as Marshal, writes a routing block, then for each face in dispatch order reads `orgs/cupel/agents/<face>.md` and writes that face's `CUPEL-REPORT`, then composes the deliverable. On the verdict path the Chamber is emulated last and is the only place a `C-<n>/CP-<k>` may appear.

## Sandbox guidance for the human

For review-path work, start Codex in its read-only sandbox so that the platform, not only the card text, prevents edits and execution. Grant workspace write only for an elevated case and only for the duration of that case. Never grant unrestricted execution; the runner shape (`python3 scripts/run_tool.py --config <cfg> --tool <entry>`) is the only command Cupel needs. The exact mode names are the platform's; verify them in the current documentation.

## What is deferred to Phase 2

Native Codex custom agents or subagents (one per card), a Codex skill wrapper for Cupel under `.agents/skills/`, Codex cloud runners producing rank-5 records, and ChatGPT packaging profiles. Each requires verification against current official documentation before it is written; none is needed to run Cupel today.
