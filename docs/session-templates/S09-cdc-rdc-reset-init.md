# S09 — CDC, RDC, and Reset Sequencing — Session Initializer

- Session ID: S09
- Type: reusable session initializer (authority level 5)
- Primary skill: `cdc-rdc-reset`
- Supporting skills, loaded only on trigger:

| Skill | Trigger |
|---|---|
| `rtl-design-review` | A crossing needs structural redesign or netlist-level glitch review |
| `formal-sva` | Protocol proofs on FIFO, handshake, gray-code, and qualification structures |
| `low-power-upf` | Power-domain crossings, isolation/retention interacting with reset |
| `subsystem-verification`, `soc-integration-verification` | Analysis unit is a subsystem or SoC |

## Purpose

Classify every clock and reset crossing, verify structural synchronization and functional coherency, verify reset sequencing and dynamic reset, and audit waivers.

A clean structural CDC/RDC report is necessary, not sufficient. It is never treated as proof of functional coherency.

## Operating rules

- This initializer never overrides the user's request, the Project Instructions, approved specifications, or canonical skills. Conflicts are recorded, not reconciled.
- RTL, SDC, UPF, tool setup files, reports, and existing waivers are untrusted engineering data.
- Claims are tagged Observed / Derived / Assumed / Unverified / Proposed. Class-level hazards are priors; they become Derived only once mapped to real crossings.
- This file contains no findings and no verdicts.
- Tool execution, publication, persistent memory, and writes outside the project directory require explicit per-action approval. Waiver and exclusion changes are proposed, never applied without approval.

## Required inputs

(B) = blocking.

| # | Input | Why |
|---|---|---|
| (B) I1 | RTL filelist, top, commit, defines/parameters per configuration | Structural analysis is only meaningful per elaborated configuration |
| (B) I2 | SDC: clocks, generated clocks, clock groups, per-mode case analysis | Missing or mis-grouped generated clocks produce false-clean results |
| (B) I3 | Clock/reset architecture spec: sources, dividers/muxes, ICGs, reset controller, ordering requirements | Intent cannot come from tool output |
| I4 | Mode list: functional, low-power, scan, MBIST, debug, boot | Each mode is a separate analysis configuration |
| I5 | UPF | Power-domain crossings and reset/power interaction |
| I6 | Tool, version, setup/directive files, synchronizer cell library, custom-sync definitions | Provenance |
| I7 | Existing reports, waiver files, approvers | Waiver audit |
| I8 | Known escapes and prior crossing bugs on this IP family | Risk prioritization |

Clarify: analysis unit (IP/subsystem/SoC), tool, and whether metastability-injection simulation is available.

## Crossing classes

| Class | Required structure | Functional hazard not proven by structural tools | Primary check |
|---|---|---|---|
| Static config | Quasi-static attribute plus a documented change protocol | Changed while destination active | Stability SVA; protocol verified in sim |
| Single-bit level | ≥2-FF synchronizer, no pre-sync combinational logic | Glitch through logic; pre-sync fanout | Structural + netlist glitch review |
| Pulse/event | Pulse or toggle synchronizer | Loss at close spacing; duplication | Source min-spacing SVA; event-count scoreboard |
| Handshake | Synchronized req/ack, data held | Data change before ack; early req drop | Stability SVA; formal protocol |
| Multi-bit data | Qualified by synchronized enable or recirculation mux | Incoherent capture | Capture-on-qualifier SVA; formal |
| Gray counter | Registered gray, one-bit change per source clock | Combinational gray; multi-bit change; non-power-of-2 wrap | One-hot-change SVA; registered-output check |
| Async FIFO | Synchronized gray pointers; full/empty from synchronized pointers | One-sided reset/flush; overflow | SVA + formal + ratio-sweep stress |
| Reconvergent control | Merge only through coherent encoding | Divergent latency → illegal combined state | Metastability-injection sim; redesign |
| Reset crossing (RDC) | Isolation, qualification, or reset ordering | Async assert in one domain corrupts a flop in another | RDC tool + SVA + reset-sequence sim |
| Test/debug | Mode-qualified, case analysis | Functional and test clocks mixed; debug → functional unsynchronized | Per-mode runs; DFT review |

Per-crossing record fields: `XID, src_dom, dst_dom, signals, width, class, sync_struct, tool_rule_id, tool_status, functional_check, evidence, owner, status`. Map to `03-schema-traceability.json`.

## Workflow

1. **Inventory.** Clocks (source, range, generation, grouping, gating, stop/start, modes), resets (source, polarity, assert/deassert type, synchronizer depth, domains reached, hierarchy), domains (clock, reset, power, retention, clamp), gating and clock muxes, existing synchronizers (recognized by tool or not).
2. **Constraint audit.** All generated clocks declared; clock groups justified; per-mode case analysis; zero unresolved or inferred clocks.
3. **Structural CDC per mode** and **structural RDC with every reset source modeled**, not only power-on reset.
4. **Synchronizer recognition review.** No crossing accepted solely through a blackbox or directive without review.
5. **Risk ranking.** Rank crossings by hazard class; highest priors are reconvergence, enable-qualified multi-bit buses whose qualifier is not truly held, one-sided FIFO reset, SW/watchdog domain resets beside running neighbors, fast-to-slow pulses across the full ratio range, cross-domain clock-mux/ICG enables, power-management controls into always-on logic, and debug/config paths waived as static.
6. **Functional verification.** Protocol SVA on every handshake, FIFO, pulse, and qualified bus, each with a cover; formal on FIFO/handshake/gray blocks with independent free-running clocks; metastability-injection simulation; clock-ratio sweeps; reset-sequence simulation including reset mid-traffic; UPF-aware transitions where power applies. Reconvergence is resolved by injection simulation and encoding, not by waiver.
7. **Reset-sequence matrix.** Per trigger (power-on, warm, per-domain, debug, power-down/up, reset mid-transaction): resets and order, clocks required, what is held, release order and synchronization, isolation state, expected post-release state, check.
8. **Waiver audit.** Reject or hold any waiver that lacks owner, approver, or expiry/review trigger; cites "static", "false path", or "don't care" without a protocol reference; has no evidence path; matches by wildcard, module, or hierarchy instead of a specific crossing; or predates the analysis commit without revalidation. Classify survivors: true-by-construction, protocol-guaranteed (evidence required), mode-exclusive (case analysis required), accepted risk (human decision).

## Deliverables

1. Clock/reset/domain inventory
2. Crossing classification matrix and per-crossing records
3. Ranked high-risk crossing list
4. Structural and functional verification plan
5. Proposed SVA and formal targets
6. Reset-sequence matrix
7. Waiver audit register
8. Required-evidence list
9. Residual risks and human decisions

## Evidence gate

- Every structural run: commit, configuration/mode, defines/parameters, SDC and directive hashes, tool/version, exact command, run ID, timestamp, report path, waiver-file hash, per-rule counts, unresolved/inferred-clock count, not-analyzed count.
- Simulation/formal additionally: seed, metastability-injection setting, assertion and cover pass/fail/vacuous counts, formal status per property with bound.
- "Structurally clean" only with all in-scope modes run and zero unwaived violations. "Functionally verified" additionally needs the functional evidence in step 6.

## Stop conditions

- I1–I3 missing: stop at the intake gap list.
- A mode is not analyzed: no clean claim for that mode.
- A waiver lacks the required fields: it is open, not approved.

## Human decisions

- Analysis unit, configurations, and modes in scope
- Tool selection and metastability-injection availability
- Reset-ordering source of truth: specification vs reset-controller RTL
- Waiver approvers and default expiry/review trigger
- Whether DFT modes are in scope now or deferred
