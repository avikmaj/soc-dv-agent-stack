# VIP Architecture & Qualification Workspace — Initialization

Date: 2026-09-24
Status: Initialized; no artifact under evaluation

## Scope

Architecture, phased implementation planning, audit, and qualification of reusable UVM VIP. No protocol, specification revision, source, or evidence has been supplied yet.

## Selected skills

- Primary: `uvm-agent-builder` (items 1–13), `vip-qualifier` (items 14–15 and the verdict).
- Supporting:
  - `spec-to-vplan` runs first, because this work is specification-driven.
  - `formal-sva` for the checker and SVA architecture.
  - `coverage-closure` for the requirement-to-coverage mapping.
  - `regression-triage` for the qualification suite.
  - `emulation-readiness` only if acceleration is in scope.
- `signoff-audit` stays out until evidence exists.

## Operating contract for feature claims

Every row in the supported-feature matrix carries one of these levels. A level is only claimed with the evidence listed.

| Level | Meaning | Evidence required |
|---|---|---|
| Declared | In the matrix and config model | Spec clause ID and configuration knob |
| Implemented | Code exists | Source commit and file/class reference |
| Exercised | Stimulus reaches it | Test name, seed, and a coverage bin hit in a named UCDB/VDB, with its run ID |
| Checked | The independent checker detects violations | A negative test injects the fault and the checker fires; the companion SVA or cover is non-vacuous |
| Qualified | Checked across the matrix | Checked on every simulator × UVM version × profile cell in scope, with pinned tool versions, reproducible commands, and fresh reports |

- A compliance claim is permitted only at Qualified, and only against an enumerated clause list for a named specification revision.
- Generated tests and source inspection reach Implemented at most.

## Intake

Items marked (B) block the architecture.

1. (B) **Protocol and specification:** the protocol, exact specification revision and issue letter, and any errata you treat as normative.
2. (B) **New or existing VIP.** If existing, supply:
   - repo and commit
   - current gate status
   - what evidence already exists
3. (B) **Profiles in and out of scope,** for example:
   - AXI4 vs AXI4-Lite vs AXI5 feature subsets such as atomics, MTE, poison, or untranslated transactions
   - an equivalent profile split for other protocols
4. (B) **Roles:** initiator, target/responder, passive monitor, and performance monitor. Also state whether an interconnect-side or dual-role agent is needed.
5. **Abstraction:**
   - pin-level only, or a TLM transport as well
   - whether a layered or semantic-to-wire split is needed, for example a CHI flit-to-transaction layer or PCIe TLP/DLLP/PHY layers
6. (B) **Concurrency:**
   - maximum outstanding per ID and in total
   - which ID classes may reorder
   - whether write-data interleaving or response interleaving is permitted
   - split transactions and retries
7. **Reset:**
   - mid-transfer reset semantics, meaning whether in-flight items are dropped, flushed, or reported
   - asynchronous vs synchronous deassert
   - partial reset of one side
8. **Error injection:**
   - protocol-illegal injection (checker-proving) vs legal-error responses
   - whether injection must be runtime-controllable per transaction
9. **Scale:**
   - number of instances
   - heterogeneous parameterization across instances (data/ID/address width)
   - whether a system-level virtual sequencer spans multiple VIPs
10. (B) **Simulators and UVM:**
    - VCS, Xcelium, and Questa versions in the matrix
    - UVM 1.1d, 1.2, IEEE 1800.2-2017, or 2020
    - whether Verilator is a secondary target
11. **Packaging:**
    - package and namespace prefix
    - whether a compile-time parameterized interface or a max-width transaction is used
    - licensing, meaning internal only or open
    - versioning policy
12. **Other scope:** formal (SVA in a bind module that is reusable in FPV?), emulation (whether a synthesizable BFM is needed), and performance-monitor metrics.

## Planned deliverables (after the (B) items are answered)

**Phase 0 — spec-to-vplan**
- Clause-level requirement IDs.
- A profile/feature matrix at Declared level.
- Ambiguities and conflicts, listed rather than reconciled.

**Phase 1 — Architecture**
- Transaction model: semantic item plus beat/flit sub-items.
- Config object with legality constraints and a `check_config()` gate.
- Layered sequencer topology.
- Driver and responder FSMs, with reset-abort arcs.
- An authoritative monitor with reconstruction rules, per-ID ordering queues, and an interleave demux.
- Checker placement: SVA in a bind-able interface checker, and transaction-level checks in the monitor, with no duplication.
- A callback/factory extension surface.
- Recording and debug.

**Phase 2 — Planning matrices**
- A requirement → check (SVA or monitor) → covergroup/bin matrix.
- A negative-test catalog, where each entry names:
  - the violation injected
  - the expected checker ID
  - the proof the check is non-vacuous

**Phase 3 — Qualification plan**
- Test tiers L0–L5.
- A seed policy.
- Simulator × UVM version × profile matrix cells.
- Per-cell exit criteria.
- The release verdict rubric.

Code comes after Phase 1 is approved.

## Findings in project collateral (Observed and Derived)

**1. The skills do not satisfy the repo's own validator.**
- Observed:
  - `04-script-validate.py` requires `## Inputs`, `## Checks`, and `## Evidence Gate`.
  - Every `02-skill-*.md` uses `## Required inputs` and `## Evidence gate`, and has no `## Checks` section.
  - Each file is about 1.2–1.4 KB, below the `len(s)<1800` threshold.
- Derived: if these are the canonical `skills/` sources, `validate.py` fails all 20 of them.
- Consequence: the 0.1.0 changelog's "production-ready" claim is Unverified, because no CI run evidence was supplied.

**2. `03-schema-regression-result.json` cannot represent multi-simulator qualification.**
- It has no fields for:
  - simulator compile/elab options or a hash of them
  - defines/plusargs
  - UVM library version
  - coverage database path
  - per-test configuration or profile
- `tool` and `tool_version` are run-level only.
- Consequence: vip-qualifier cannot reconstruct a matrix cell from this record. Proposal: a schema 1.1 extension.

**3. `03-schema-verification-plan.json` has no fields for specification revision, profile, or clause reference.**
- Requirement → clause traceability for a compliance claim therefore has nowhere to live.

**4. `03-schema-traceability.json` status stops at `passing`.**
- There is no state that separates Exercised, Checked, and Qualified.
- The feature matrix above would be lossy against it.

Fixes 2–4 are schema changes, and fix 1 needs skill edits. None of them will be applied without approval.

## Release-readiness result: NOT READY

There is no VIP, specification baseline, or evidence under review. This is the default verdict, not an assessment of any artifact.

## Next step

Answer the (B) items. For an existing VIP, provide the source and its latest regression artifacts; the audit will start there instead of a greenfield architecture.
