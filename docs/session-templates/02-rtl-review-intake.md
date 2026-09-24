# Microarchitecture & RTL Review — Session Initialization

Date: 2026-09-24
Primary skills: microarchitecture-review, rtl-design-review
Supporting (on demand): lint-synth-closure, formal-sva, cdc-rdc-reset, low-power-upf
Deliverable: findings register. No code edits until the findings and the intended behavior are confirmed.

---

## 1. Scope

This session is set up for microarchitecture and synthesizable RTL review.

- **Primary skills:** microarchitecture-review and rtl-design-review.
- **Supporting skills:** lint-synth-closure, formal-sva, cdc-rdc-reset or low-power-upf. Each is added only when its report or crossing is in scope.
- **Deliverable:** a findings register, not code edits. Edits wait until the findings and the intended behavior are confirmed.

## 2. Classification of supplied material

None of the supplied material is design material. That means no architecture spec, microarchitecture spec, interface spec, RTL, lint, synthesis, CDC/RDC or formal report, and no patch.

What was supplied is the review stack itself:

| Group | Content |
|---|---|
| 01-* | Control-plane docs: evidence contract, methodology, security policy, architecture |
| 02-* | Twenty skill definitions |
| 03-* | Artifact schemas and templates: vplan, traceability, regression result, waiver |
| 04-* | Repo tooling: bootstrap, run_tool, sync_adapters, validate, tests, CI, packaging |

The design review is blocked on inputs. See section 5 for the checklist.

## 3. Stack findings

### STK-001: Skill files do not satisfy validate.py

| Field | Value |
|---|---|
| Class | Robustness (infrastructure) |
| Severity | Medium |
| Confidence | High |
| Evidence class | Observed |
| Location | `04-script-validate.py.txt`, the `required=[...]` list and the `len(s)<1800` check, compared against all uploaded `02-skill-*.md` |
| Invariant | Canonical skills must pass `scripts/validate.py`, as required by `04-contributing.md` |
| Observed | The validator requires `## Inputs`, `## Checks` and `## Evidence Gate` (capital G), plus at least 1800 characters. The skills use `## Required inputs` and `## Evidence gate`, have no `## Checks` section, and are about 1.3–1.5 KB each. |
| Failure scenario (Derived) | `python scripts/validate.py` reports missing sections and "insufficient detail" for all 20 skills. CI fails. The "production-ready" claim in `04-changelog.md` is Unverified. |
| Minimal correction | Choose one: (a) align the skill headers and add a `## Checks` section to each skill, or (b) relax the validator. This is a human decision. |
| Validation evidence | Output of `python scripts/validate.py` and `python -m unittest discover -s tests -v`, with the commit and a timestamp |

### STK-002: run_tool.py environment allowlist may strip the EDA environment

| Field | Value |
|---|---|
| Class | Robustness |
| Severity | Low |
| Confidence | Medium |
| Evidence class | Derived |
| Location | `04-script-run-tool.py.txt`, the line that builds `env` from `environment_allowlist` |
| Failure scenario | If `PATH`, `LM_LICENSE_FILE`/`SNPSLMD_LICENSE_FILE` or `VCS_HOME` are not in the allowlist, the tool binary fails to resolve or to license. |
| Minimal correction | List the required variables in `project-config.example.json` under `environment_allowlist`. |
| Validation evidence | A `run_tool.py` run of a real tool entry that exits 0 against the licensed simulator |

## 4. Finding record format

Every design finding carries these fields:

- ID
- Class: Correctness defect / Robustness / Performance / Style
- Severity: S1–S4
- Confidence: High / Med / Low, tied to the evidence class
- Evidence class: Observed / Derived / Assumed / Unverified
- Location: file / module / signal / line
- Requirement or invariant
- Failure scenario, as a concrete cycle sequence or configuration
- Recommended minimal correction
- Proposed SVA or test
- Required validation evidence

Severity scale:

| Level | Definition |
|---|---|
| S1 | Functional or security failure reachable in a supported configuration |
| S2 | Failure under a corner case or configuration, or silent data corruption that needs unusual timing |
| S3 | Robustness, observability or verification-hook gap |
| S4 | Style or maintainability |

Findings map onto `03-schema-traceability.json`. Waiver candidates map onto `03-schema-waiver.json`.

Review axes (all 12 by default; severity is weighted toward axes 1–8):

1. Requirements and interface consistency
2. Datapath widths, signedness, casts, truncation, extension, overflow and saturation
3. Combinational completeness, latch inference, multiple drivers and combinational loops
4. Sequential semantics, reset values, enables, priorities and simultaneous events
5. FSM legality, unreachable states, recovery and illegal-state behavior
6. Handshake stability, backpressure, buffering, ordering, fairness, starvation, overflow and underflow
7. Parameter and configuration corner cases
8. Clock, reset, power and asynchronous crossings
9. X propagation and simulation-versus-synthesis differences
10. Synthesizability and inferred-implementation risks
11. Performance, observability, testability and verification hooks
12. Security, privilege, access control and fault containment

## 5. Review-input checklist

### 5.1 Identity and configuration
- [ ] Repo, branch and commit (or CL). For a patch, the base and head commits.
- [ ] Exact filelist (`.f`), top module, `+define`s, include dirs and package compile order
- [ ] Parameter sets in scope, with the supported configurations listed and the legal and illegal parameter corners stated
- [ ] Files that are generated or vendor. Their sources and generators are reviewed; the outputs are not edited.

### 5.2 Specifications (with revision IDs)
- [ ] Architecture spec: features, modes, security and privilege model
- [ ] Microarchitecture spec covering:
  - block diagram
  - pipelines and latency
  - buffer depths and the credit model
  - arbitration policy, including the fairness guarantee
  - ordering rules
  - error and recovery behavior
  - performance targets
- [ ] Interface specs covering:
  - protocol and issue (AXI4/AXI5/ACE/CHI and so on)
  - profile: data, address, ID and user widths; outstanding limits; ordering model; exclusives and atomics; response codes; burst types; narrow and unaligned support; wake-up and low-power signals
  - deviations from the standard
- [ ] Clock/reset table, per domain:
  - frequency ratios
  - sync or async relationship
  - reset sources, assertion and deassertion type, and release sequencing
  - clock gating and clock stop/start behavior
- [ ] Power intent: UPF plus the power-state table, if a low-power review is in scope
- [ ] CSR map: IP-XACT or spreadsheet with access types, reset values and side effects, if the block has registers
- [ ] Known spec conflicts or open questions. Leave them unreconciled; they will be flagged, not resolved.

### 5.3 RTL
- [ ] Complete source set for the scoped hierarchy: packages, interfaces, macros and all instantiated submodules
- [ ] Library cells, memories and sync-cell wrappers, or at least their behavioral models and port semantics
- [ ] Synthesis target: ASIC library or FPGA family. This changes how reset style, latches, RAM inference and initial blocks are rated.

### 5.4 Reports (each with tool, version, command, run ID and timestamp)
- [ ] **Lint:** tool and ruleset, the full violation list (not only a summary), and the current waiver file
- [ ] **Synthesis:**
  - log
  - `check_design` / `check_timing` output
  - inferred latch, register, RAM and multiplier reports
  - constant and unloaded register removals
  - SDC
  - timing summary, if performance is in scope
- [ ] **CDC/RDC:**
  - setup: clocks, resets, constraints, modes
  - violation list
  - waivers with owner and expiry
- [ ] **Formal:**
  - property list
  - assumptions and constraints
  - engine, depth and bounds
  - proven, CEX, undetermined and vacuity/cover results
  - CEX traces

### 5.5 Verification context
- [ ] Existing vplan or requirement IDs, and the SVA already bound to the block
- [ ] Coverage holes, if available
- [ ] Open bugs and known intermittents against this block
- [ ] Waveforms or a log, if any finding should be anchored to an observed failure

### 5.6 Review scope decisions
- [ ] Mandatory versus best-effort review axes
- [ ] Whether security, privilege and fault containment apply to this block
- [ ] Pass/fail criteria for the review, for example "no open S1/S2 without an owner"

## 6. Human decisions required

1. **Confidentiality:** confirm that the shared RTL and specs are cleared for this project context. They will be kept out of reusable memory, public examples and external services.
2. **STK-001:** choose whether to align the skills or relax the validator.
3. **First review target:** name the material type and commit. A microarchitecture spec before RTL is the preferred order when both exist.
