# Department Map

Cupel has fourteen departments and three offices. Departments hold domain expertise and issue findings; offices hold the mechanics that keep a case honest (candidate identity, evidence records, stack integrity). Each unit is realised by one or more cards (`execution-agent-map.md`). Departments never share a card; a card never serves two departments.

## Departments

| Department | Holds | Typical inputs | Never |
|---|---|---|---|
| `charter-bench` | Verification architecture and methodology; specification and requirements intelligence; the closure contract (which requirements, which configurations, which evidence area, before "done"); traceability ownership | Specifications, interface documents, errata, existing plans, intake forms | Derives a requirement from RTL, VIP, tests, or models without recording it as proposed and pending human approval |
| `design-reading-room` | RTL structural and behavioural review; microarchitecture; lint and synthesizability readiness; reset, X, width, FSM, clocking | RTL, parameter packages, filelists, lint and synthesis reports | Adjudicates a crossing (hands it to `domain-crossing-desk`) |
| `interconnect-rulebook` | Protocol and interface compliance at the declared revision; VIP integration, configuration, and qualification; bridge and conversion behaviour | Protocol specifications, VIP configuration, monitors and checkers | Cites a protocol rule without specification, revision, and section |
| `testbench-works` | SystemVerilog and UVM engineering; stimulus, sequences, scenarios; RAL; reuse and simulator portability; scheduling semantics | UVM sources, tests, RAL models, run scripts | Treats the absence of `UVM_ERROR` as a check |
| `comparator-desk` | Scoreboards, checkers, reference models, predictors; ordering semantics; matching; drain; checker vacuity | Scoreboards, models, comparison policies | Takes expected values from the DUT |
| `proof-bench` | Assertions and SVA; formal property verification; assumptions and overconstraint; vacuity and cover reachability; proof-status vocabulary | SVA sources, bind files, formal scripts and reports, counterexamples | Reports bounded or undetermined as proven |
| `coverage-desk` | Functional, code, and assertion coverage; hole classification by cause; exclusions and waivers as controlled artifacts; requirement states from records | Covergroups, reports, merged databases, exclusion files | Infers closure from an aggregate percentage |
| `regression-yard` | Simulation and regression infrastructure; run configurations; seeds; determinism; provenance and retention; the only execution door (runner face) | Run scripts, `.soc-dv/config.json`, CI workflows and logs, result files | Treats a zero-test, filtered, or off-revision run as evidence |
| `divergence-lab` | Failure triage; waveform and log debug; root-cause attribution (DUT, testbench, specification, environment) | Logs, first-failure signatures, waveforms, seeds | Lets a plausible story stand in for a reproduced one |
| `system-assembly-floor` | SoC and subsystem integration; HW/SW and firmware co-verification; NoC system behaviour; address maps, interrupts, DMA, boot, coherency | Integration RTL, IP-XACT, firmware, NoC configuration, C tests | Invents an ordering, coherency, fairness, or progress requirement |
| `domain-crossing-desk` | CDC and RDC; reset assertion and deassertion; synchroniser protocols; low-power intent, isolation, retention, power states | CDC/RDC reports, clock and reset trees, UPF, power-aware logs | Accepts a non-power-aware simulation as low-power evidence |
| `load-bench` | Performance, stress, QoS; latency and bandwidth measurement; workload provenance; specification-derived acceptance | Workloads, monitors, measurement reports | Invents a workload or a target |
| `threat-desk` | Security verification: privilege model, partitioning, firewalls, debug access, key and secret paths, negative testing | Security specifications, firewall configuration, negative test lists | Requests a real key, password, token, or credential |
| `challenge-chamber` | Independent audit and red team; claim challenge; ledger reconciliation; ceiling computation; the only source of verdicts and Chamber pass identifiers | Every report of the case, the closure contract, the Vault's records | Edits anything; accepts a claim because it was popular |

## Offices

| Office | Holds | Never |
|---|---|---|
| `intake-registry` | Candidate pinning (every source commit, configuration hash, tag) or the declaration UNPINNED; the case log; the evidence manifest | Decides CURRENT or STALE; mints a record |
| `evidence-vault` | The only minting of `C-<n>/EV-<area>-<k>` records; provenance completeness; CURRENT or STALE (non-arbitrable); ranks 4 to 6; UNVERIFIED-RECORD marking | Mints from prose, summaries, badges, or belief; runs a tool |
| `stack-stewardship` | Check-only parity and validation of Cupel and the stack it lives in, through a fixed command allowlist | Syncs, regenerates, or writes anything |

## Coverage of required organisational areas

The organisation was required to cover twenty-three areas. Each maps to exactly one primary unit:

| Area | Primary unit |
|---|---|
| Leadership and routing authority | `case-marshal` (entry point) under human authority |
| Verification architecture and methodology | `charter-bench` |
| Specification and requirements intelligence | `charter-bench` |
| RTL structural and behavioural intelligence | `design-reading-room` |
| Protocol and interface compliance | `interconnect-rulebook` |
| SystemVerilog and UVM engineering | `testbench-works` |
| VIP integration and configuration | `interconnect-rulebook` |
| Stimulus, sequences, scenarios | `testbench-works` |
| Scoreboards, checkers, reference models | `comparator-desk` |
| Assertions and SVA | `proof-bench` |
| Formal verification | `proof-bench` |
| Functional, code, assertion coverage | `coverage-desk` |
| Simulation and regression infrastructure | `regression-yard` |
| Debug, waveform, root cause | `divergence-lab` |
| SoC and subsystem integration | `system-assembly-floor` |
| HW/SW and firmware verification | `system-assembly-floor` |
| Low power and UPF | `domain-crossing-desk` |
| CDC, RDC, reset | `domain-crossing-desk` |
| Performance, stress, QoS | `load-bench` |
| Security verification | `threat-desk` |
| Requirements-to-test traceability | `charter-bench` with `intake-registry` |
| Verification closure and signoff readiness | `challenge-chamber` (ceiling-setter) with `evidence-vault` |
| Independent quality, audit, red team | `challenge-chamber` |

Combining low power with CDC/RDC/reset (both are boundary-crossing disciplines with the same waiver mechanics) and VIP integration with protocol compliance (the VIP is the protocol's executable rulebook) keeps the department count at fourteen without leaving an area unowned.

## Relationship to the stack's skills

Departments consume the twenty canonical skills under `skills/` as method; Cupel adds organisation, evidence discipline, and challenge on top of them. A card names the skills it consults. A skill never relaxes a card, and a card never restates a skill's workflow; it points to it.
