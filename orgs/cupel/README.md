# Cupel

**Cupel** is an agentic ASIC/SoC design-verification organisation that runs on top of this stack's twenty canonical skills. A cupel is the small porous cup used in fire assay: the sample goes in, the heat is applied, and what remains is what was actually there. Cupel treats verification claims the same way. Expansion, for those who want one: **Confidence Under Proof Engineering Layer**.

```yaml
organization_id: cupel
organization_name: Cupel
version: 0.2.0
schema_version: "1.0"
created_date: 2026-09-25
core_path: orgs/cupel
supported_adapter_versions: {claude-code: 0.2.0, claude-project: 0.2.0, codex-agents-md: 0.2.0, portable-prompt-protocol: 0.2.0}
```

Status: **Phase 1, rebuilt.** The accepted design was implemented and statically validated once before (2026-09-25) in a session whose files were lost uncommitted; this tree is a rebuild from the accepted design, with the owner's requested v2 layout. `docs/rebuild-notes.md` states exactly what is verbatim from the accepted design, what was reconstructed, what was validated in this rebuild, and what was not.

## The one rule

> A verdict is bounded above by what has been registered against the named candidate, never by how much has been thought, argued, or agreed about it.

Full text and consequences: `docs/law.md`. Reasoning does not equal verification: analysis, review, debate, agreement, majority, and model confidence can hold a verdict where it is or push it lower; only an evidence record minted by the Evidence Vault from a reproducible tool run at the pinned candidate can raise it.

## Shape

```text
human  ->  case-marshal  ->  14 departments + 3 offices  ->  evidence-vault  ->  challenge-chamber  ->  one deliverable
```

- 14 departments: charter-bench, design-reading-room, interconnect-rulebook, testbench-works, comparator-desk, proof-bench, coverage-desk, regression-yard, divergence-lab, system-assembly-floor, domain-crossing-desk, load-bench, threat-desk, challenge-chamber (`docs/department-map.md`).
- 3 offices: intake-registry (pins the candidate), evidence-vault (the only minter of evidence records), stack-stewardship (check-only parity and validation).
- 28 cards: 14 review faces, 9 drafting faces, 1 runner, 3 offices, 1 entry point (`docs/execution-agent-map.md`, `docs/role-map.md`). Read-only is the default everywhere; drafting and execution need verbatim human sentences (`docs/modes.md`).
- Two paths: review (no verdict) and verdict (Registry first, Chamber last, always) (`docs/operating-model.md`).
- One evidence model: claim classes, ranks 1..6, twelve-field provenance, CURRENT or STALE, the ceiling computation, PASS / CONDITIONAL / NOT READY (`docs/evidence-and-verdict-model.md`).

## Layout

```text
orgs/cupel/
  README.md  CHANGELOG.md  cupel.json          identity, version, face inventory, patterns, tripwires
  docs/                                        law, operating model, departments, roles, cards, evidence and verdicts, modes, invocation, extension, rebuild notes
  agents/                                      28 canonical cards (Claude Code subagent format: name, description, tools)
  schemas/                                     case-request, department-report, evidence-record, dissent-ledger-entry, final-verdict
  examples/                                    one validated instance per schema plus two walkthroughs
  adapters/                                    README (contract, capability summary); claude/, codex/, portable/
  tools/check_parity.py                        card shape and byte-for-byte mirror check; --sync regenerates mirrors
  tools/validate_cupel.py                      law verbatim, patterns, tripwires, sentences, pointer blocks, schemas, examples, links, unsafe patterns
  tests/test_cupel_static.py                   positive and negative tests for both tools
.claude/agents/cupel/                          byte-identical mirror of orgs/cupel/agents/ (Claude Code carrier)
```

Pointer edits outside this tree: `CLAUDE.md` (Cupel block), `AGENTS.md` (Cupel routing section), `README.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/harnesses.md`. Nothing under `skills/`, `scripts/`, `tests/`, `schemas/`, or `.github/` is touched.

## Using it

Claude Code (primary carrier):

```bash
claude --agent cupel-case-marshal
claude --agent cupel-case-marshal -p "Use Cupel to review tb/axi_env/ for scoreboard vacuity and phase hygiene."
```

Codex and other `AGENTS.md` readers: the routing section in `AGENTS.md` plus `adapters/portable/prompt-protocol.md`. Claude Projects, ChatGPT Projects, any chat surface, any LLM: `adapters/portable/chat-kernel.md` as instructions and `adapters/portable/knowledge-bundle/` as knowledge. Phrasing is the same everywhere (`docs/invocation-guide.md`):

```text
Use Cupel to review this UVM environment.
Ask Cupel's protocol department to review this AXI implementation.
Ask the Chamber to challenge this PASS claim.
Elevate Cupel/testbench-works to implementation for tb/**; I approve file edits under that path.
Run Cupel/regression-yard-runner: .soc-dv/config.json tool lint; I approve this single execution.
```

## Validating this tree

```bash
python3 orgs/cupel/tools/check_parity.py
python3 orgs/cupel/tools/validate_cupel.py
python3 -m unittest discover -s orgs/cupel/tests -v
python3 scripts/validate.py && python3 scripts/sync_adapters.py --check && python3 -m unittest discover -s tests -v
```

The first three are Cupel's own; the last line proves the stack is unaffected. Static validation is not execution evidence: it shows the organisation is self-consistent, not that any agent behaves as its card says. Behavioural evidence comes from fresh-process routing runs (`adapters/claude/claude-code.md`, "Proving that a card loaded"; suggested set in `docs/rebuild-notes.md`).

## Editing

Cards are canonical under `agents/`; after editing one, run `python3 orgs/cupel/tools/check_parity.py --sync` and the validators. The `CLAUDE.md` and `AGENTS.md` blocks are canonical in `adapters/claude/claude-md-section.md` and `adapters/codex/agents-md-section.md`; the validator refuses drift. Extension rules and version bumps: `docs/extension-guide.md`.

## Phase 2 (deferred, all Unverified)

Native Codex and ChatGPT agents, cloud runners, ChatGPT packaging profiles, GitHub Copilot and VS Code adapter, Cursor adapter, Grok, Kimi, and Nemotron carriers beyond the generic protocol, the full platform capability matrix, CI integration of the Cupel checks, bootstrap support, and tripwire reserved-word exclusions. Each waits for verification against current official documentation, per the repository's policy.
