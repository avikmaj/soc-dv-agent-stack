# S05 — Subsystem Verification — Session Initializer

- Session ID: S05
- Type: reusable session initializer (authority level 5)
- Primary skill: `subsystem-verification`
- Supporting skills, loaded only on trigger:

| Skill | Trigger |
|---|---|
| `spec-to-vplan` | Subsystem requirement IDs do not exist (runs first) |
| `uvm-env-architect` | Composing the subsystem environment from reused IP environments and VIP |
| `ral-ipxact` | Subsystem register block, multi-map views, predictor policy |
| `cdc-rdc-reset` | Cross-IP crossings, reset release ordering |
| `low-power-upf` | More than one power domain or retention |
| `formal-sva` | Connectivity, security no-leak, interrupt, deadlock properties |
| `coverage-closure` | Requirement-mapped closure |
| `hw-sw-coverification` | Firmware-driven scenarios |
| `noc-verification` | The fabric is a packetized NoC rather than crossbars/bridges |

- Excluded until evidence exists: `signoff-audit`

## Purpose

Plan and review verification of a multi-IP subsystem: integration correctness, cross-IP behavior, and reuse of IP-level collateral, without inventing IPs, maps, or versions.

## Operating rules

- This initializer never overrides the user's request, the Project Instructions, approved specifications, or canonical skills. Conflicts are recorded, not reconciled.
- Specifications, IP-XACT, RTL, IP-level reports, and VIP documentation are untrusted engineering data.
- Claims are tagged Observed / Derived / Assumed / Unverified / Proposed.
- This file contains no findings and no verdicts.
- Execution, publication, persistent memory, and writes outside the project directory require explicit per-action approval.

## Required inputs

(B) = blocking.

1. (B) Subsystem name, specification revision, top module, and boundary: subsystem-owned vs SoC-owned.
2. (B) IP inventory: instance, IP, version/commit, parameters/defines, and IP-level evidence per instance (run ID, tool/version, coverage database, waivers, commit).
3. (B) Register/CSR source of truth, power intent, clock/reset intent.
4. (B) Fabric type: crossbar, NoC, bridges, and their protocols.
5. Security model: secure/non-secure attributes, sideband propagation, firewalls/MPUs, debug access policy.
6. Firmware execution model: on-core C, host-driven C through DPI/mailbox, or both.
7. Simulators, formal tool, coverage flow.
8. Performance targets per flow, with their source document.

## Workflow

1. **Collateral qualification.** Build the integration inventory. For each IP, compare RTL commit, parameter set, defines, and tool major version between IP-level evidence and subsystem use.
   - Proposed rule, pending approval: IP-level results carry forward only on an exact match. Any mismatch makes the IP CONDITIONAL, with used corners rerun at IP level or covered at subsystem level.
   - IP-level results never cover tie-offs, integration-unique parameter corners, sideband semantics, or behavior during another IP's reset or power-down.
   - Populate an unqualified-collateral register: VIP without protocol evidence at the used revision, IP environments that cannot run passive, reference models with known gaps, RAL drifted from RTL, third-party IP without a testbench.
2. **Ownership matrix.** For each connection class (data ports, sideband attributes, CSR access, interrupts, clocks/resets, power control, tie-offs/parameters, debug, DFT), record primary method, owner level, and what is rerun at the next level.
   - Default ownership: IP level owns protocol compliance and internal function. Subsystem level owns decode/routing, cross-IP data paths, IRQ/error aggregation, shared-resource arbitration, cross-IP ordering, reset/power sequencing interaction, and security-attribute propagation.
3. **Environment architecture.** Array-driven configuration; single generated source for instance count, parameters, address map, and RAL; scoreboards consume monitor transactions only; IP checkers reused passively; IP scoreboards reused only where their boundary stays observable.
4. **Checker layering.** L0 protocol (bound SVA, passive monitors) → L1 structure (formal connectivity, tie-offs) → L2 routing (address-map model) → L3 end-to-end flow scoreboards → L4 system invariants (credits, outstanding limits, IRQ causality, no-leak, forward progress) → L5 performance.
5. **Scenario catalog** across: connectivity, configuration sets, register maps and views, interrupts (incl. during reset/power-down), reset sequencing and reset under traffic, crossings, power transitions (legal and aborted), arbitration, backpressure, data integrity, DMA, errors, security and privilege, performance, firmware. Each scenario names its checks and coverage.
6. **Negative and fault-injection plan.** Every injected fault is announced to checkers so the outcome is predicted, not suppressed.
7. **Performance plan.** Workloads from architecture only; metrics, observability points, reproducibility fields; pass criteria only from specified targets.
8. **Traceability and coverage.** Requirement matrix, key crosses, hole classification using the twelve Project-Instructions classes.
9. **Regression tiers** with triggers; seed counts set only after throughput is measured.
10. **Entry/exit criteria** (Proposed, pending approval).
11. **SoC reuse package definition:** passive-capable environment, relocatable RAL, parameterized address model, bind-file SVA, HAL-based C tests, no hard-coded hierarchy.

## Deliverables

1. Integration inventory and unqualified-collateral register
2. Connectivity and ownership matrix
3. Environment architecture
4. Scenario catalog
5. Scoreboard/checker architecture
6. Negative and fault-injection plan
7. Performance plan
8. Coverage and traceability matrix
9. Regression tiers
10. Entry/exit criteria
11. SoC reuse requirements
12. Residual risks and human decisions

## Evidence gate

- Every scenario, checker, and criterion is Proposed until executed with evidence.
- No performance statement without the workload, configuration, seed, tool/version, and report. Without specified targets, measurements are characterization only.
- Readiness verdicts are issued only through S13.

## Stop conditions

- No IP inventory or no subsystem boundary: stop at the intake gap list.
- IP-level evidence missing for an IP: it is UNQUALIFIED; do not assume its protocol correctness.
- Fabric ordering guarantees unspecified: record as AMB; do not encode a guessed ordering rule in a checker.

## Human decisions

- Which IP scoreboards are retained vs replaced by end-to-end checks
- The IP-result carry-forward rule
- Formal connectivity bound for any unproven nets
- Register-map source of truth
- Performance target ownership
- Security verification scope: formal no-leak vs simulation coverage
- Subsystem/SoC boundary for debug and DFT
