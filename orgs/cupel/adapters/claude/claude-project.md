# Claude Projects Adapter

Claude Projects (claude.ai) have project instructions and project knowledge but no repository checkout, no tool execution, and no native subagents. Cupel runs there as an emulated organisation: the hosting model plays the Marshal and each dispatched face in turn, following the portable protocol, with evidence supplied as pasted raw output. This is the same carrier used for ChatGPT Projects and other chat surfaces; the only Claude-specific parts are the field names below.

```yaml
platform: Claude Projects (claude.ai), also applicable to Claude.ai custom instructions
supported_surfaces: project chats; the SoC DV Engineering Studio project is one such surface
instruction_mechanism: Project Instructions (CONFIRMED: this repository's owner runs a project with instructions)
repository_context: none live; Project Knowledge holds uploaded snapshots (CONFIRMED); the knowledge bundle under portable/knowledge-bundle/ is uploaded as four files
agent_mechanism: none native (CONFIRMED for Projects); emulated per portable/prompt-protocol.md
delegation_mechanism: none; sequential emulation inside one reply or across replies
parallelism: none; departments are emulated one after another, each reading its card text from the knowledge bundle before writing its report
tool_execution: none; the runner face does not exist here; evidence is pasted raw output only
persistent_context: Project Instructions and Project Knowledge (CONFIRMED)
limitations:
  - nothing can be executed, so every record the Vault mints is at best report-only (rank 4) and the ceiling is at best CONDITIONAL
  - the model that plays the Chamber also played the departments; independence is procedural (card read in full, report written fresh), not structural
  - uploaded knowledge is a snapshot; the Registry declares UNPINNED unless the pin is stated in the request
capability_mapping:
  CAP_REPO_READ: no (uploaded snapshots only)
  CAP_FILE_EDIT / CAP_COMMAND_EXECUTION / CAP_TERMINAL: no
  CAP_NATIVE_SUBAGENT / CAP_PARALLEL_AGENT / CAP_BACKGROUND_AGENT: no
  CAP_PERSISTENT_INSTRUCTIONS: yes (CONFIRMED)
  CAP_PROJECT_CONTEXT: yes, as uploaded knowledge (CONFIRMED)
  CAP_TOOL_RESULT_CAPTURE: pasted raw output only
fallback_strategy: this adapter is itself the fallback for every surface without agents
invocation_examples: see below
schema_version_targeted: "1.0"
```

## Installation

1. Paste `orgs/cupel/adapters/portable/chat-kernel.md` (its body, without the leading explanation) into the Project Instructions, below any existing instructions. The kernel narrows; it never relaxes what is already there.
2. Upload the four files of `orgs/cupel/adapters/portable/knowledge-bundle/` to Project Knowledge, keeping their names (`01-law.md` .. `04-invocation.md`).
3. Optionally upload `orgs/cupel/docs/evidence-and-verdict-model.md` and `orgs/cupel/docs/operating-model.md` for the full definitions; the bundle is sufficient to operate.

Do not upload confidential RTL, logs, or specifications to a project whose knowledge is shared with anyone who should not see them; the repository's confidentiality rule applies to Project Knowledge.

## Operating in a project chat

```text
Use Cupel to review the attached UVM environment for scoreboard vacuity and phase hygiene.
Use Cupel to give a verdict on candidate <sha>, configuration hash <hash>, tag <tag>; the regression summary is pasted below.
Ask the Chamber to challenge the attached signoff memo.
```

The reply follows `04-invocation.md`: Marshal routing block, then one `CUPEL-REPORT` per emulated face in dispatch order (Registry first and Chamber last on the verdict path), then the composed deliverable. The Chamber section is written after re-reading `01-law.md`; if the reply runs out of room before the Chamber, the deliverable says `chamber_pass: Chamber not run` and the next reply continues.

## Relationship to the SoC DV Engineering Studio project

That project's instructions already define claim classes, evidence policy, verdict words, and session initializers S00..S14. Cupel is compatible with them: its claim classes and verdicts are the same words, its Chamber is a stricter form of S13 signoff audit, and its departments map onto S01..S12. Where the project instructions and this adapter both speak, the project instructions win (they sit at authority level 2; Cupel documents sit with methodology at level 6).
