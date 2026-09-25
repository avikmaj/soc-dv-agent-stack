# Execution Agent Map: the 28 cards

Canonical cards live under `orgs/cupel/agents/<face>.md`. The Claude Code adapter carries byte-identical copies under `.claude/agents/cupel/<face>.md`; `orgs/cupel/tools/check_parity.py` verifies the mirror and `--sync` regenerates it. Every card's frontmatter has exactly three keys: `name` (`cupel-<face>`), `description` (at most 200 characters), and `tools` (the face class's envelope). Bodies are between 1800 and 9000 characters. Machine-readable identity for all cards is in `orgs/cupel/cupel.json`.

| Card (`name`) | File | Class | Unit | Tools | Dispatch when |
|---|---|---|---|---|---|
| `cupel-case-marshal` | `case-marshal.md` | entry point | — | Agent | Every request; the human speaks to this card |
| `cupel-intake-registry` | `intake-registry.md` | office | intake-registry | Read, Grep, Glob | First on the verdict path |
| `cupel-evidence-vault` | `evidence-vault.md` | office | evidence-vault | Read, Grep, Glob | After departments, before the Chamber, on the verdict path |
| `cupel-stack-stewardship` | `stack-stewardship.md` | office | stack-stewardship | Read, Grep, Glob, Bash | Requests about Cupel or the stack; parity and validation checks |
| `cupel-challenge-chamber` | `challenge-chamber.md` | review | challenge-chamber | Read, Grep, Glob | Last on the verdict path, always; appended on the review path on a tripwire or by name |
| `cupel-charter-bench` | `charter-bench.md` | review | charter-bench | Read, Grep, Glob | Plans, requirements, traceability; second on the verdict path (closure contract) |
| `cupel-charter-bench-drafting` | `charter-bench-drafting.md` | drafting | charter-bench | Read, Grep, Glob, Edit, Write | Writing vplans, traceability, intake forms under elevation |
| `cupel-design-reading-room` | `design-reading-room.md` | review | design-reading-room | Read, Grep, Glob | RTL, microarchitecture, lint questions |
| `cupel-design-reading-room-drafting` | `design-reading-room-drafting.md` | drafting | design-reading-room | Read, Grep, Glob, Edit, Write | RTL or filelist edits under elevation |
| `cupel-interconnect-rulebook` | `interconnect-rulebook.md` | review | interconnect-rulebook | Read, Grep, Glob | Protocol, VIP, compliance questions |
| `cupel-interconnect-rulebook-drafting` | `interconnect-rulebook-drafting.md` | drafting | interconnect-rulebook | Read, Grep, Glob, Edit, Write | VIP configuration or checker edits under elevation |
| `cupel-testbench-works` | `testbench-works.md` | review | testbench-works | Read, Grep, Glob | UVM, sequences, RAL, scheduling questions |
| `cupel-testbench-works-drafting` | `testbench-works-drafting.md` | drafting | testbench-works | Read, Grep, Glob, Edit, Write | Testbench edits under elevation |
| `cupel-comparator-desk` | `comparator-desk.md` | review | comparator-desk | Read, Grep, Glob | Scoreboard, checker, model questions |
| `cupel-comparator-desk-drafting` | `comparator-desk-drafting.md` | drafting | comparator-desk | Read, Grep, Glob, Edit, Write | Scoreboard or model edits under elevation |
| `cupel-proof-bench` | `proof-bench.md` | review | proof-bench | Read, Grep, Glob | SVA and formal questions |
| `cupel-proof-bench-drafting` | `proof-bench-drafting.md` | drafting | proof-bench | Read, Grep, Glob, Edit, Write | Property or formal script edits under elevation |
| `cupel-coverage-desk` | `coverage-desk.md` | review | coverage-desk | Read, Grep, Glob | Coverage, hole, exclusion questions |
| `cupel-coverage-desk-drafting` | `coverage-desk-drafting.md` | drafting | coverage-desk | Read, Grep, Glob, Edit, Write | Covergroup or exclusion edits under elevation |
| `cupel-regression-yard` | `regression-yard.md` | review | regression-yard | Read, Grep, Glob | Regression, flow, provenance questions |
| `cupel-regression-yard-runner` | `regression-yard-runner.md` | runner | regression-yard | Read, Grep, Glob, Bash | One approved `.soc-dv/config.json` entry per verbatim approval sentence |
| `cupel-divergence-lab` | `divergence-lab.md` | review | divergence-lab | Read, Grep, Glob | Failure triage, waveform, root cause |
| `cupel-system-assembly-floor` | `system-assembly-floor.md` | review | system-assembly-floor | Read, Grep, Glob | SoC, subsystem, HW/SW, NoC questions |
| `cupel-system-assembly-floor-drafting` | `system-assembly-floor-drafting.md` | drafting | system-assembly-floor | Read, Grep, Glob, Edit, Write | Integration testbench or C test edits under elevation |
| `cupel-domain-crossing-desk` | `domain-crossing-desk.md` | review | domain-crossing-desk | Read, Grep, Glob | CDC, RDC, reset, UPF questions |
| `cupel-load-bench` | `load-bench.md` | review | load-bench | Read, Grep, Glob | Performance, stress, QoS questions |
| `cupel-load-bench-drafting` | `load-bench-drafting.md` | drafting | load-bench | Read, Grep, Glob, Edit, Write | Monitor or workload configuration edits under elevation |
| `cupel-threat-desk` | `threat-desk.md` | review | threat-desk | Read, Grep, Glob | Security verification questions |

Counts: 14 review faces (13 departments plus the Chamber), 9 drafting faces, 1 runner, 3 offices, 1 entry point; 28 cards.

## Card anatomy

Every card has the same spine so that a reader, a validator, or another platform's adapter can find the same things in the same order:

1. Title and one-paragraph identity.
2. The law (first sentence for departments and the Registry, Runner, and Stewardship; full text for the Marshal, the Chamber, and the Vault).
3. Envelope: face class, tools, mode, and the never-list.
4. What you receive (the `CUPEL-DISPATCH` fields).
5. Unit-specific sections (mission, what you read, what you check, skills consulted; stations for the Chamber; minting and currency for the Vault; routing, dispatch, merge, and verdict integrity for the Marshal).
6. How you classify what you say (claim classes and ranks).
7. Tripwires.
8. Dissent.
9. Output: one `CUPEL-REPORT` block.
10. Stop and report when.

## Stable identifiers

The card `name` is the stable identifier and is independent of any display name in prose ("Charter Bench", "the Vault"). Adapters and dispatch blocks refer to cards by `name` only. Renaming a card is a breaking change to the organisation's schema version (`cupel.json`).
