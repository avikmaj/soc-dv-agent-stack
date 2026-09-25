# Portable Prompt Protocol

The universal way to run Cupel on any model or agent that has no native subagents: a chat model, an API-driven LLM, a coding agent without delegation, or a future platform. The protocol needs only ordinary prompts, plus repository or pasted access to the Cupel cards where available. The logical organisation is unchanged; what changes is that one model plays the Marshal and every dispatched face in turn.

## 1. Loading

Whoever hosts the model (a human, a wrapper script, an orchestration framework) provides, in this order of preference:

1. The full canonical documents (`orgs/cupel/docs/law.md`, `operating-model.md`, `evidence-and-verdict-model.md`, `modes.md`) and the cards under `orgs/cupel/agents/`, readable by the model; or
2. The knowledge bundle (`knowledge-bundle/01-law.md` .. `04-invocation.md`) uploaded or pasted; or
3. At minimum, `chat-kernel.md` pasted as the system or project instruction.

Less material means less precision, never a different organisation. The kernel alone is enough to keep the law, the read-only default, the block formats, and the Chamber-last rule.

## 2. The request

```text
LOAD ORGANIZATION: Cupel
MODE: READ_ONLY                     # or PLANNING; IMPLEMENTATION and VALIDATION need the verbatim sentences below
DELIVERABLE: review                 # or verdict
CANDIDATE: UNPINNED                 # or: repo@sha (one per repository), config_hash: ..., tag: ...
DEPARTMENTS: auto                   # or an explicit list of department names
TARGETS: <paths, or "pasted below">
EVIDENCE: <paths, run ids, or "pasted raw output below">
ELEVATION: none                     # or the verbatim sentence: Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.
APPROVED_COMMANDS: none             # or one or more verbatim sentences: Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.
TASK: <what you want>
EVIDENCE POLICY: Do not claim tool success without supplied or generated tool evidence; report NOT READY as an absence of evidence.
```

Plain language works too (`Use Cupel to review this UVM environment.`); the block form is recommended for verdicts because it forces the candidate pin to be stated.

## 3. Emulation order

The model, as Marshal, writes a routing block:

```text
CUPEL-ROUTING
case: C-<n>
path: review | verdict
tripwires_detected: <words with sources, or none>
dispatch_order: <faces in order>
```

Then, for each face in order, it **reads that face's card in full** (from disk, from the knowledge bundle, or from `02-departments.md` when only the bundle is present) and writes one `CUPEL-REPORT` block for that face, as if it had received the `CUPEL-DISPATCH` below. It does not read any later face's card before finishing the current report, and a later face does not revise an earlier face's report.

```text
CUPEL-DISPATCH
case: C-<n>
face: cupel-<face>
mode: read-only | planning | implementation | validation | challenge
path: review | verdict
elevation: none | <verbatim sentence>
approved_commands: none | <verbatim sentences>
platform: generic | claude-project | chatgpt-project | codex | claude-code
candidate: UNPINNED | PINNED <details>
targets: ...
evidence: ...
open_ledger: <prior entries verbatim, or empty>
claim_classes: Observed, Derived, Assumed, Unverified, Proposed
ledger_id_form: ^C-[0-9]+/DL-[a-z][a-z-]*[a-z]-[0-9]{3}$
tripwires_detected: ...
task: ...
```

Order on the review path: routed departments, then `challenge-chamber` if a tripwire fired or the request names it. Order on the verdict path, fixed: `intake-registry`, `charter-bench`, routed departments, `evidence-vault`, `challenge-chamber` last.

## 4. Reports

Each face's `CUPEL-REPORT` carries, in order: `face`, `case`, `mode`, `path`, `claims_of_success`, `findings` (by claim class: Observed, Derived, Assumed, Unverified, Proposed; each with id, statement, severity, rank 1..6, evidence refs, affected files, affected requirements), `evidence_records`, `requirement_states`, `ledger_entries`, `ceiling_suggestion`, `verdict`, `ceiling_computation`, `human_decisions`, `validation_performed`, `next_commands`, `residual_gaps`, `ledger_control`, `chamber_pass`. For every face except the Chamber, `verdict`, `ceiling_computation`, and `chamber_pass` are exactly `NONE`. The Vault's report additionally lists every record it minted with all twelve provenance fields and its CURRENT or STALE status.

## 5. Evidence without execution

When the host cannot execute anything, the only admissible material is raw tool output pasted into the request. The Vault mints from it as `report-only` (rank 4) when all twelve provenance fields can be filled from the pasted material, and as `UNVERIFIED-RECORD` otherwise. The ceiling is therefore at most CONDITIONAL on such a surface, and it is NOT READY whenever the candidate is UNPINNED. The model states this plainly; it never simulates a tool run, never invents output, and never reports a percentage it did not see.

## 6. The deliverable

The Marshal composes one document: header (`case`, `path`, `mode`, `platform`, `candidate`; `not adjudicated; no verdict` on the review path), faces in order, merged findings by rank and class, evidence records verbatim from the Vault, requirement states, the dissent ledger verbatim, the verdict lines copied verbatim from the Chamber (or exactly `chamber_pass: Chamber not run`), human decisions, validation performed and not performed, next commands, residual gaps, and a closing `STATUS · EVIDENCE · NEXT` line.

## 7. Integrity rules the emulation must keep

- Only the Chamber's ceiling-setter station, on the verdict path, writes a verdict or a `C-<n>/CP-<k>`; the Marshal copies, never composes.
- Dissent entries are carried verbatim: no renumbering, merging, deleting, or rewording. A collision or malformed identifier is preserved and recorded as a defect in a new `DL-case-marshal-<seq>` or `DL-challenge-chamber-<seq>` entry.
- Tripwire words (pass, passed, proven, closed, covered, compliant, clean, signoff, ready, verified, success, closure, complete, green) are scanned lexically without negation handling; a hit appends Chamber scrutiny and does nothing else.
- Read-only unless the verbatim elevation sentence is present; no execution unless the verbatim approval sentence is present; no commit, push, pull request, network, installation, or permission bypass under any circumstances.
- If the reply runs out of room, the deliverable so far is emitted with `chamber_pass: Chamber not run` and the next reply continues from the next face in order.

## 8. Orchestration frameworks and API use

A framework (any agent SDK, a NIM-hosted model, a local open-weight model behind an OpenAI-compatible endpoint) runs Cupel by giving each face its card as the system prompt and the `CUPEL-DISPATCH` as the user message, in the order above, and by giving the Marshal's card plus the collected reports for composition. Parallel department calls are allowed; Registry-first and Chamber-last are not negotiable. Tool results captured by the framework are handed to the Vault as raw text with their provenance fields; the framework never fills a provenance field the tool did not print. A model-neutral wrapper of this kind is the intended Phase 2 adapter for Nemotron and similar model families.
