# Coverage-Closure Session Initialization

Date: 2026-09-24
Status: Initialized, no coverage evidence ingested
Closure readiness: **NOT READY** (all layers: Insufficient evidence)

---

## 1. Scope

This session covers requirements-driven coverage analysis and closure.

- **Observed:** the project knowledge contains the methodology, skills, schemas, templates and scripts.
- **Observed:** it contains no coverage data. There are no UCDB/VDB/IMC databases, hole reports, merge logs or vplan instance.
- **Consequence:** every layer below is Unverified until the provenance manifest (Section 3) is satisfied.

## 2. Selected Skills

The primary skill is **coverage-closure**.

Supporting skills are selected for each hole according to its root-cause class:

| Hole class | Supporting skill(s) | Closure vehicle |
|---|---|---|
| Missing stimulus | uvm-agent-builder, uvm-env-architect | New or extended sequences, virtual sequences |
| Constraint blockage | uvm-agent-builder | Constraint audit, solver trace, `rand_mode` / `constraint_mode` layering |
| Missing configuration | spec-to-vplan, subsystem-verification, soc-integration-verification | Config-matrix extension, new build targets |
| Insufficient observability | uvm-env-architect, waveform-debug | Monitor, probe or sample-point fix |
| Checker/model defect | uvm-env-architect, waveform-debug | Scoreboard or reference-model fix plus guard test |
| Coverage-model defect | coverage-closure | Covergroup, bin, cross or sample-event correction |
| DUT defect | rtl-design-review, waveform-debug | Bug filed; the hole stays open until the fix is verified |
| Unreachable by construction | formal-sva, lint-synth-closure | Formal unreachability proof or constant-propagation evidence, then an exclusion |
| Unsupported feature | spec-to-vplan | Scope decision recorded against the requirement |
| Candidate exclusion | coverage-closure, then signoff-audit | Controlled waiver record |
| Insufficient evidence | regression-triage | Rerun with provenance |
| Clock/reset domain | cdc-rdc-reset | RDC/CDC-specific stimulus and checks |
| Power domain | low-power-upf | UPF state/transition coverage |
| CSR/register | ral-ipxact | RAL-driven access/reset/side-effect sequences |
| NoC/interconnect | noc-verification | QoS, ordering, congestion, deadlock scenarios |
| Firmware-driven | hw-sw-coverification | C-test scenarios, mailbox/barrier sequencing |

signoff-audit is used only after evidence exists.

## 3. Provenance Manifest (hard gate before analysis)

Every item must be Observed from an artifact. Items that are only Assumed are listed as such.

| # | Item | Required content |
|---|---|---|
| 1 | Revisions | DUT commit; TB/VIP/reference-model commits; vplan and requirement-baseline revision; exclusion-file revision and sha256 |
| 2 | Tools | Simulator and version per run; coverage tool and version (urg / imc / vcover); formal tool and version if cover results are used |
| 3 | Build | Compile/elab command lines; `+define`s; parameter overrides per configuration; coverage switches (e.g. `-cm line+cond+fsm+tgl+branch+assert`); hierarchy scoping (cm_hier / covfile); covergroup options (`per_instance`, `goal`, `at_least`, `weight`, `get_inst_coverage` usage) |
| 4 | Regression | Test list; per test: seed, status, run ID and timestamp, first error, coverage DB path |
| 5 | Merge procedure | Exact merge command; union vs test-associated mode; design-checksum mismatch policy; exclusion of failing / timed-out / killed tests; per-configuration merge separation; the merge log |
| 6 | Goals / policy | Approved signoff policy and revision; per-metric goals; per-instance vs per-type metric; exclusion approval authority |

### Merge failure modes to rule out explicitly

- Merging DBs built from different design checksums without a mapping strategy.
- Coverage contributed by failing, timed-out or killed tests.
- Type-level covergroup coverage masking an unexercised IP instance.
- Toggle coverage inflated or deflated by tied-off ports on parameterized instances.
- Covergroups sampling during reset.
- Assertion coverage counted from attempts or vacuous successes rather than real matches.
- Formal "undetermined" results being read as unreachable.

## 4. Layered Analysis Method

| Layer | Extraction | Acceptance basis |
|---|---|---|
| Requirements | Each REQ-ID mapped to tests, assertions, coverpoints and formal targets, with status | Every P0/P1 REQ closed with current evidence or an approved disposition |
| Functional | Per-bin hits per instance and configuration; zero and low-hit bins | Goal met per instance, not only per type |
| Assertions | Real-success count, vacuity, disabled / `$assertoff` scope, failures | Non-vacuous success on every requirement-mapped property |
| Code (line/branch/cond/expr) | Holes mapped to requirements or to dead logic | Every hole dispositioned |
| FSM | States, transitions, illegal-transition checks | Transitions covered, or reset/illegal arcs proven unreachable |
| Toggle | 0→1 and 1→0 per bit, excluding tie-offs by configuration | Tie-offs justified by configuration evidence, not blanket exclusion |
| Cross | Illegal/ignore bins checked against spec; empty crosses | Illegal/ignore bins traceable to spec clauses |
| Formal cover | Covered / unreachable (proven) / undetermined | Undetermined counts as open |
| Configuration | Parameter and define matrix vs configurations actually run | Every supported configuration has its own evidence |
| Error / negative | Injected errors, protocol violations, reset-abort, timeouts, recovery | Each error requirement shows both detection and recovery |
| Performance | Latency and throughput bins with workload definition | Reproducible workload with pinned seed and configuration |

Closure is never inferred from a single aggregate percentage.

## 5. Hole Disposition Rules

- **One class, fully tagged.** Each significant hole gets exactly one primary class from Section 2. It also gets an evidence tag (Observed / Derived / Assumed / Unverified), an owner, and a target closure vehicle.
- **Risk-based ranking.** Holes are ranked by requirement priority × failure consequence × likelihood of masking a bug. They are not ranked by bin count or percentage impact.
- **Unreachable needs evidence.** "Unreachable by construction" requires either:
  - a formal unreachability proof with a run ID; or
  - constant-propagation or configuration evidence tied to a specific design revision.
- **Reasoning alone is not enough.** Reasoning without that evidence gives **Candidate exclusion** status only.

## 6. Exclusion and Waiver Record Requirements

Every proposed exclusion must carry:

| Field | Content |
|---|---|
| id | Unique waiver ID |
| category | coverage / cdc / rdc / lint / formal / protocol / other |
| scope | Hierarchy path, instance, configuration, bins or lines |
| justification | Spec clause or construction argument |
| evidence | Proof run ID, report path, design commit |
| owner | Responsible engineer |
| approver | Per signoff policy |
| expiry | Date |
| review_trigger | e.g. any RTL change under the scoped hierarchy; hash mismatch on the excluded object |
| residual_risk | Named risk accepted by the exclusion |
| status | proposed / approved / expired / rejected |

### Schema gaps (Observed in project files; extensions are Proposed, not applied)

- **03-schema-waiver.json:** lacks `scope`, `residual_risk`, `review_trigger`, and design-revision binding (`design_commit` / object hash). `expiry` alone is insufficient.
- **03-schema-traceability.json:** the status enum lacks `excluded`, `unreachable` and `unsupported`, so dispositioned holes cannot be distinguished from `waived`.
- **03-schema-regression-result.json:** lacks per-test `coverage_db`, `defines` and `parameters`, and run-level `merge` and `exclusion_files` provenance.
- **03-template-verification-plan.json:** its signoff criterion does not cover coverage goals, per-instance and per-configuration closure, or exclusion approval.

Canonical schemas are not modified without approval.

## 7. Readiness Criteria

**PASS** requires all of the following:
- Provenance is complete and current, at the same commits as the signoff candidate.
- All P0/P1 requirements are closed.
- All per-instance and per-configuration goals are met.
- No undetermined formal covers remain on mapped targets.
- All exclusions are approved and unexpired.
- No open DUT or checker defects remain against covered items.

**CONDITIONAL** means everything required for PASS is met except:
- remaining gaps are limited to P2 items, or to approved time-bound exclusions;
- each such gap has a named residual risk and an owner.

**NOT READY** applies if any of the following holds:
- a provenance gap;
- an open P0/P1 hole;
- an unapproved exclusion;
- coverage merged from failing runs;
- reliance on an aggregate percentage.

**Current status: NOT READY.** All layers are classed as Insufficient evidence.

## 8. Required Inputs

1. **Merged coverage reports** in text form, plus the exact merge command and merge log:
   - VCS: `urg -format text -show tests`
   - Xcelium: `imc` `report -detail -inst -all`
   - Questa: `vcover report -details -cvg -assert -fsm`
2. **Hole reports.** Per-instance hole reports for functional, code, FSM, toggle and assertion coverage.
3. **Regression results.** Test, seed, status, run ID and per-test DB paths.
4. **Build data.** Compile and elab logs, or build configuration, showing defines, parameters and coverage switches per configuration.
5. **Vplan.** Vplan or requirement list with REQ-IDs, priorities and revision.
6. **Exclusions.** Exclusion files (`.el`, vRefine, or `.do` exclude scripts) and any existing waivers.
7. **Signoff policy.** Approved signoff policy with goals and approval authority.
8. **Formal results.** Formal cover results and run metadata, if they are used.

## 9. Open Clarifications

- **Simulators.** Is signoff on a single simulator, or is cross-simulator merging in scope? The recommendation is per-simulator evidence with no cross-simulator merge.
- **Signoff metric.** Per-instance or per-type for multi-instance IPs?
- **Design level.** IP, subsystem or SoC? This determines whether integration-level connectivity and configuration coverage are in scope.

## 10. Deliverables (produced once inputs arrive)

1. Coverage provenance
2. Requirement-closure matrix
3. Ranked hole analysis
4. Root-cause classification
5. Proposed tests / sequences / formal targets
6. Coverage-model corrections
7. Exclusion and waiver review
8. Expected coverage deltas
9. Rerun plan
10. Closure readiness: PASS / CONDITIONAL / NOT READY

## 11. Project Hygiene Note

The uploaded `02-skill-*` files would fail the stack's own `validate.py`:

- **Section heading mismatch:** they use `## Required inputs`, but the validator requires `## Inputs`.
- **Missing section:** there is no `## Checks` section.
- **Casing mismatch:** they use `## Evidence gate`, but the validator requires `## Evidence Gate`.
- **Length:** they are likely under the 1800-character minimum.

This does not block coverage analysis. The canonical sources should be fixed before any CI claim is made about the skill set.
