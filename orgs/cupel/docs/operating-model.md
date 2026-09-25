# Operating Model

Cupel is a verification organisation expressed as text: one law, seventeen units, twenty-eight agent cards, five schemas, and a small number of adapters that carry the same organisation onto different AI platforms. This document describes how a request moves through it. Definitions of evidence, ranks, and verdicts live in `evidence-and-verdict-model.md`; unit responsibilities in `department-map.md`; card classes in `role-map.md`; the card inventory in `execution-agent-map.md`; modes and approval sentences in `modes.md`.

## Layers

```text
LEVEL 0  Human authority        the engineer: requests, elevates, approves runs, accepts dissent, signs off
LEVEL 1  Case Marshal           routes, dispatches, merges by rank, composes; judges nothing
LEVEL 2  Units                  14 departments + 3 offices (intake-registry, evidence-vault, stack-stewardship)
LEVEL 3  Faces                  review / drafting / runner / office / entry-point card classes with fixed tool envelopes
LEVEL 4  Cards                  28 concrete agent definitions under orgs/cupel/agents/
         Evidence engine        Evidence Vault mints records; Registry pins the candidate
         Challenge              Challenge Chamber runs last; only its ceiling-setter station writes a verdict
         Adapters               Claude Code, Codex/AGENTS.md, Projects/chat kernel, generic prompt protocol
```

Platform adapters translate the layers onto a platform's mechanisms. They never add a unit, remove a rule, or change a word of the law.

## A case, end to end

1. **Request.** The engineer writes in plain language (`invocation-guide.md`). On a platform with a native agent mechanism the request reaches `cupel-case-marshal`; elsewhere the engineer or the hosting model plays the Marshal by following `adapters/portable/prompt-protocol.md`.
2. **Routing.** The Marshal classifies the request onto one of two paths and maps its vocabulary onto departments with the alias table below. Routing is a bookkeeping act; it is never an adjudication of any claim.
3. **Dispatch.** Every unit receives one `CUPEL-DISPATCH` block (schema fields in `evidence-and-verdict-model.md` under Blocks). Independent departments run in parallel where the platform allows and sequentially otherwise; their reports are kept separate either way.
4. **Reports.** Every unit returns exactly one `CUPEL-REPORT` block (`schemas/department-report.schema.json`). Findings carry a claim class and a rank. Dissent is raised as ledger entries. Departments suggest a ceiling; they never write a verdict.
5. **Evidence.** On the verdict path the Intake Registry pins the candidate and builds the evidence manifest first, and the Evidence Vault mints records after the departments have reported. The Vault's CURRENT-or-STALE call is non-arbitrable.
6. **Challenge.** The Challenge Chamber runs last on the verdict path, always, and is appended on the review path when a tripwire fired or the request named it. Only its ceiling-setter station computes the ceiling, issues a Chamber pass identifier, and writes the verdict.
7. **Deliverable.** The Marshal merges by rank, preserves the ledger byte-for-byte, copies the verdict lines verbatim from the Chamber or writes `chamber_pass: Chamber not run`, and hands back one document ending with `STATUS · EVIDENCE · NEXT`.

## The two paths

**Review path.** Used when the deliverable is a review, a plan, an explanation, or a debug investigation and no input asserts success. Only the routed departments are dispatched. The Chamber is appended when a tripwire fired or the request names it; on this path the Chamber runs its claim-challenger and ledger-reconciler stations only and writes `verdict: NONE (ceiling-setter not run)`. The deliverable is headed `not adjudicated; no verdict`.

**Verdict path.** Used when the deliverable is a verdict, a readiness, closure, or signoff answer, or when any input asserts success (a report, a log, or a person stating that something passed, is proven, is covered, or is done). The dispatch order is fixed:

```text
intake-registry -> charter-bench (closure contract) -> routed departments -> evidence-vault -> challenge-chamber (last, always)
```

Path selection is the Marshal's reading of what is being asked. It is not triggered by tripwire words (see Tripwires): a request that says "do not claim PASS" contains a tripwire and asserts nothing, so it stays on the review path with the Chamber appended.

## Alias table

Plain words map to departments. When several match, several are dispatched. Offices are never reached by alias: the Registry and the Vault are dispatched by the verdict path, and Stack Stewardship whenever the request concerns Cupel or the stack itself.

| Words in the request | Department |
|---|---|
| audit, red team, challenge, dissent, signoff readiness, PASS claim | `challenge-chamber` |
| architecture, methodology, plan, vplan, specification, requirements, traceability | `charter-bench` |
| RTL, microarchitecture, lint, synthesizability, X propagation, FSM | `design-reading-room` |
| protocol, interface, VIP, AXI, AHB, APB, CHI, PCIe, USB, DDR, Ethernet, compliance | `interconnect-rulebook` |
| UVM, SystemVerilog, testbench, sequences, stimulus, RAL, config_db, factory | `testbench-works` |
| scoreboard, checker, reference model, predictor, comparison | `comparator-desk` |
| SVA, assertion, property, formal, proof, vacuity, counterexample | `proof-bench` |
| coverage, coverpoint, bin, hole, exclusion, waiver | `coverage-desk` |
| regression, flow, simulation infrastructure, seeds, CI, intermittent | `regression-yard` |
| debug, triage, waveform, root cause, failure signature, first failure | `divergence-lab` |
| SoC, subsystem, integration, HW/SW, firmware, boot, interrupt, DMA, NoC, address map | `system-assembly-floor` |
| CDC, RDC, reset, clock domain, synchronizer, UPF, low power, power domain, isolation, retention | `domain-crossing-desk` |
| performance, latency, bandwidth, throughput, QoS, stress, congestion, starvation | `load-bench` |
| security, privilege, firewall, secure, non-secure, TrustZone, access control, key path | `threat-desk` |

Typical compound routes:

```text
AXI ordering failure        -> interconnect-rulebook, comparator-desk, divergence-lab
UVM phase or objection bug  -> testbench-works, regression-yard, divergence-lab
Coverage hole               -> coverage-desk, testbench-works, charter-bench
CDC finding                 -> domain-crossing-desk, design-reading-room, system-assembly-floor
UPF issue                   -> domain-crossing-desk, design-reading-room, proof-bench
Performance regression      -> load-bench, interconnect-rulebook, system-assembly-floor
Signoff or PASS claim       -> verdict path: registry, charter-bench, routed units, vault, chamber
```

## Marshal controls

Three controls, adopted from the accepted design after fresh-process routing tests, bind the Marshal and are checked by the Chamber:

- **Verdict integrity.** The Marshal copies `verdict`, `ceiling_computation`, `chamber_pass`, and any `C-<n>/CP-<k>` identifier verbatim from the final Chamber report; when the Chamber did not run it writes exactly `chamber_pass: Chamber not run` and no verdict line. It never composes, reserves, infers, predicts, or suggests any of them. Only the ceiling-setter station may.
- **Ledger integrity.** Dissent identifiers have the form `C-<case>/DL-<raising-face>-<three-digit-seq>`. The Marshal may order entries; it never renames, renumbers, merges, deletes, or rewrites them. Malformed or colliding entries are preserved byte-for-byte and a separate `C-<case>/DL-case-marshal-<seq>` entry records the defect. Two parallel departments emitting the same sequence number is a collision to record, not a mistake to repair.
- **Conservative tripwires.** The tripwire words listed in `modes.md` are scanned lexically in the request, the targets, and every report, without interpreting negation. A hit appends Chamber scrutiny and nothing else. A tripwire never selects the verdict path, never grants PASS, and never assigns a Chamber pass identifier. Reserved words inside department reports (for example `NOT READY` in a `ceiling_suggestion`) do trigger scrutiny; exclusions for them are deferred to Phase 2 and recorded in `rebuild-notes.md`.

## Parallelism and independence

Departments are logically independent: none reads another's report before writing its own, and the Marshal never summarises one department's evidence for another. Where a platform offers parallel delegation the Marshal uses it for the department stage only; the Registry precedes and the Vault and Chamber follow in strict order. Where a platform offers no delegation, the same order is executed sequentially by whoever plays the Marshal, with each unit's card read in full before its report is written.

## State

Cupel is stateless by default. A project may keep a case log by convention at `.soc-dv/cupel/cases/C-<n>/`; the Intake Registry reads it when present and returns prior OPEN or ACCEPTED dissent verbatim. Writing to the case log is a human action or an elevated drafting action; no face writes it on its own initiative.
