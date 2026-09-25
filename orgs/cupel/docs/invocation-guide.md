# Invocation Guide

The engineer never needs to know the card topology. Cupel is invoked in plain language; the Marshal (native or emulated) turns the words into routed work. This guide gives the universal phrasing, then the platform-specific entry points of the Phase 1 adapters.

## Universal phrasing

```text
Use Cupel to review this UVM environment.
Use Cupel in read-only mode.
Ask Cupel's protocol department to review this AXI implementation.
Run Cupel's architecture, protocol, scoreboard, coverage and debug departments on tb/ and rtl/.
Ask the Chamber to challenge this PASS claim.
Use Cupel to investigate this regression failure: logs/regress_2026-09-24/.
Use Cupel to give a verdict on candidate <sha> with configuration hash <hash> and tag <tag>.
Elevate Cupel/testbench-works to implementation for tb/**; I approve file edits under that path.
Run Cupel/regression-yard-runner: .soc-dv/config.json tool lint; I approve this single execution.
```

Department words are resolved by the alias table in `operating-model.md`; "protocol department" reaches `interconnect-rulebook`, "the Chamber" or "audit" reaches `challenge-chamber`, and so on. Naming a platform mode is optional:

```text
Use Cupel in Claude Code repo mode.
Use Cupel in Codex repo mode.
Use Cupel in Project mode.
Use Cupel using generic LLM mode.
```

## What to include in a request

A request that wants a verdict should carry the candidate pin (every commit, the configuration hash, a tag), the targets, and the evidence supplied (paths, run identifiers, or pasted raw output). Without the pin the Registry declares UNPINNED and the ceiling is NOT READY; that is a correct outcome, not a failure. A request that wants a review needs only the targets and the question. The structured form of a request is the `CUPEL-REQUEST` block (`schemas/case-request.schema.json`, example in `examples/`); it is optional on every platform and recommended whenever a verdict is wanted.

## Claude Code

Primary carrier: the cards under `.claude/agents/cupel/` and the pointer block in `CLAUDE.md`. Entry point:

```bash
claude --agent cupel-case-marshal
claude --agent cupel-case-marshal -p "Use Cupel to review tb/axi_env/ for UVM phase and objection hygiene."
```

Inside an ordinary session, `Use the cupel-case-marshal agent to ...` also reaches the Marshal; see `adapters/claude/claude-code.md` for the delegation limits that make `--agent` the validated path.

## Codex and other AGENTS.md readers

Primary carrier: the Cupel routing section in `AGENTS.md` plus `adapters/portable/prompt-protocol.md`. The hosting agent plays the Marshal by following the protocol; departments are emulated sequentially by reading each card in full before writing its report. Phrasing is unchanged.

## Claude Projects, ChatGPT Projects, and any chat surface

Primary carrier: `adapters/portable/chat-kernel.md` pasted into the project or system instructions, with the four files of `adapters/portable/knowledge-bundle/` uploaded as knowledge. Evidence is pasted as raw output; nothing is executed. Phrasing is unchanged; the deliverable is the same block structure, and an unrun Chamber is reported as `chamber_pass: Chamber not run`.

## Generic LLM mode

For any model with no native agents and no repository access, the request is the whole interface:

```text
LOAD ORGANIZATION: Cupel
MODE: READ_ONLY
DEPARTMENTS: charter-bench, interconnect-rulebook, comparator-desk, coverage-desk, divergence-lab, challenge-chamber
TASK: Review this verification environment (pasted below).
EVIDENCE POLICY: Do not claim tool success without supplied or generated tool evidence; report NOT READY as an absence of evidence.
```

The full protocol, including the emulation order and the report block, is `adapters/portable/prompt-protocol.md`.

## Reading a Cupel deliverable

Every deliverable has the same shape: header, faces dispatched, findings by rank and class, evidence records, requirement states, the dissent ledger, the verdict lines (or `chamber_pass: Chamber not run`), human decisions, validation performed and not performed, next commands, residual gaps, and a closing `STATUS · EVIDENCE · NEXT` line. Read the ledger and the residual gaps first; they are where the honest uncertainty lives.
