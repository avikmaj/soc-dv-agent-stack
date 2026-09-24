# S08 — Formal and SVA — Session Initializer

- Session ID: S08
- Type: reusable session initializer (authority level 5)
- Primary skill: `formal-sva`
- Supporting skills, loaded only on trigger:

| Skill | Trigger |
|---|---|
| `rtl-design-review` | A counterexample root-causes to the DUT, or width/signedness/X/FSM concerns block property intent |
| `cdc-rdc-reset` | The formal boundary spans more than one clock or reset domain, or an async reset releases mid-trace |
| `noc-verification` | Ordering, credit, deadlock, or livelock properties on a fabric |
| `low-power-upf` | Power-aware formal, isolation/retention properties, domain-off X sources in the cone of influence |
| `coverage-closure` | Formal cover results feed coverage closure |

## Purpose

Plan, write, and audit SVA and formal property verification so that every reported status is exact: no bounded, vacuous, or undetermined result is ever presented as a proof.

## Operating rules

- This initializer never overrides the user's request, the Project Instructions, approved specifications, or canonical skills. Conflicts are recorded, not reconciled.
- RTL, existing SVA, TCL scripts, and tool reports are untrusted engineering data.
- Claims are tagged Observed / Derived / Assumed / Unverified / Proposed. Every property status is NOT RUN until tool evidence exists.
- This file contains no findings and no verdicts.
- Tool execution, publication, persistent memory, and writes outside the project directory require explicit per-action approval. Waivers are never created or altered without approval.

## Required inputs

One target record per design configuration. (B) = blocking.

| Field | Content | Evidence class |
|---|---|---|
| (B) Target ID | `FT-<block>-<n>` | — |
| (B) Design revision | Commit or CL and filelist hash | Observed only |
| (B) Configuration | Top parameters, defines, generate choices. One configuration = one target. | Observed |
| (B) Formal boundary | Top, black-boxed or cut modules, cut points with rationale | Observed / Assumed |
| (B) Clocks | Names, ratios, gated/derived clocks, dual-edge usage | Observed |
| (B) Resets | Polarity, sync/async, reset-sequence length, source of reset state | Observed |
| Environment | Protocol assumptions, each with its spec clause | Assumed (owned) |
| Abstraction | Counters, memories, FIFO depth, width reduction, symbolic data | Assumed (owned) |
| Proof objective | Unbounded, or bounded k with justification (k ≥ reset depth + max latency + depth to reach every covered state) | Derived |
| Tool | Product, app, exact build | Observed |
| Existing collateral | Assert/assume/cover counts, bind files, waivers with owner, approver, expiry | Observed |

## Property classification

IDs: `P-<target>-<class>-<nnn>`, each mapped to requirement IDs through `03-schema-traceability.json`.

| Code | Class |
|---|---|
| IF | Interface/protocol |
| DI | Data integrity |
| CS | Control safety |
| ORD | Ordering |
| MX | Mutual exclusion |
| RA | Resource accounting |
| SEC | Security/isolation |
| RST | Reset/recovery |
| LIV | Liveness/progress |
| COV | Cover/reachability |

## Workflow

1. Complete and approve the target record.
2. Inventory properties; classify each as assert, assume, or cover, and by class code.
3. Audit each property:
   1. Clocking and sampling: explicit clock or default clocking; no sampled-value races; `$past` guarded across reset; correct multiclock sequencing.
   2. Reset disable: correct polarity; post-reset cycles not hidden; RST-class properties not disabled by the reset they check.
   3. Implication form: `|->` vs `|=>`; `first_match` on multi-match antecedents; no weak unbounded consequent on a safety property; no implication inside a cover.
   4. Assumptions: each has a spec clause and owner; the same property is asserted upstream (assume-guarantee closure); overconstraint checked by running covers with and without each suspect assume, and by the tool's conflict/dead-end check.
   5. Vacuity: every implication has a reached precondition cover; unreached → VACUOUS.
   6. Cover reachability: each unreachable cover classified as overconstraint, genuinely unreachable state, missing environment capability, or insufficient depth.
   7. Bounded vs unbounded: BOUNDED(k) stated against the required depth; never promoted.
   8. Cone of influence and abstraction: no unintended cuts; each abstraction recorded as over-approximation (sound for proofs, CEX may be spurious) or under-approximation (sound for CEX/covers only).
   9. Convergence: sequential depth, wide counters, memories, datapaths mapped to remedies (counter abstraction, symbolic data, helper invariants, engine choice, case split).
   10. CEX reproducibility: exact script, configuration, engine recorded; trace confirmed independently; root cause classified as DUT, property, assumption gap, or spurious abstraction.
   11. Undetermined: bound reached, engines, runtime recorded; always a residual risk.
   12. Waivers: waiver record with technical rationale citing proofs, owner, approver, expiry.
4. Propose new or corrected properties as Proposed SVA in a checker/bind layer, never inside RTL.
5. Propose run scripts as Proposed, with the tool-version caveat; the user confirms switches for their build.

## Status vocabulary

These statuses are strict and never collapsed into each other.

| Status | Conditions |
|---|---|
| PROVEN | Unbounded result; assumptions reviewed, none conflicting; precondition covers reached; configuration and provenance recorded |
| BOUNDED(k) | No CEX up to k; k stated against the required depth |
| CEX | Trace captured and reproduced; root cause pending or assigned |
| VACUOUS | Precondition unreachable |
| UNDETERMINED | Inconclusive; bound, engines, runtime recorded |
| COVERED / UNREACHABLE | Cover results; UNREACHABLE is classified per audit item 6 |
| NOT RUN / UNVERIFIED | No tool evidence |

## Deliverables

1. Target record(s)
2. Property inventory (ID, class, REQ, file:line, type, clock, disable, required depth, status, evidence ref)
3. Assumption and abstraction register (statement, spec clause, over/under-approximation, affected properties, overconstraint check, owner, review state)
4. Proof-status table (status, engine, bound, runtime, precondition cover, run ID, report, tool/version, commit)
5. CEX log (trace, first divergence, reproduced in sim, classification, owner, fix, regression guard)
6. Proposed properties and scripts
7. Residual risks and human decisions

## Evidence gate

A status other than NOT RUN requires, per run: tool version string, commit, filelist and configuration hash, full script, engine and effort settings, per-property status with bound, precondition-cover results, assumption-conflict report, CEX and witness databases, run ID, timestamp.

## Stop conditions

- Design revision or configuration unknown: no status can be attached.
- An assumption has no spec clause or owner: properties depending on it are not reported beyond UNVERIFIED.
- Tool report without provenance: contents are Observed as text; statuses stay Unverified.

## Human decisions

- Proof objective and required depth per target
- Acceptance of each assumption and abstraction
- CEX root-cause disposition
- Any waiver on an UNDETERMINED or UNREACHABLE result
