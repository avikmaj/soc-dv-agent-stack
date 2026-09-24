# Specification Intake Template — spec-to-vplan
Version: 0.1 (2026-09-24). Fill every field or mark UNKNOWN / N/A with an owner. UNKNOWN on a MANDATORY item blocks plan generation.

## A. Document baseline (MANDATORY)
| Doc ID | Title | Type (arch/uarch/IF/CSR/UPF/SDC/std) | Revision | Date | Status (draft/approved) | Owner | Authoritative for | Supersedes |
|---|---|---|---|---|---|---|---|---|
| DOC-001 | | | | | | | | |

- External standards referenced (name, exact version/issue, profile/subset used, licence OK to cite?):
- Precedence rule when docs conflict (e.g. CSR XML > uarch > arch):
- Confidentiality class of each doc (internal/customer/public) — governs what may appear in examples:

## B. DUT identity (MANDATORY)
- DUT name / top module / RTL revision (commit or CL):
- Hierarchy level: IP | subsystem | SoC | chiplet
- Instances in context (count, per-instance parameters):
- Boundary: what is DUT vs. modelled vs. stubbed:
- Delivery form: RTL / encrypted / netlist / 3rd-party IP (+ vendor collateral version):

## C. Configuration space (MANDATORY)
| Param/define | Range/legal set | Default | Ship configs | Must-verify corners | Illegal combos |
|---|---|---|---|---|---|

- Build-time vs. run-time (CSR/strap/fuse) configuration split:
- Configuration signoff set (the exact list signoff applies to):

## D. Interfaces and protocols (MANDATORY per port)
| Port/bus | Protocol + version/issue | Role (mgr/sub/both) | Widths (addr/data/id/user) | Outstanding/ordering model | Optional features used | Clock | Reset | Power domain |
|---|---|---|---|---|---|---|---|---|

- Sideband/interrupt/DMA-request/debug/strap signals with timing:
- Endianness, address map, alias/hole behaviour, response on decode error:

## E. Clocks, resets, power (MANDATORY)
- Clocks: name, freq range, source, ratio constraints, gating, stop/start rules:
- Crossings list (src→dst, data type: bit/pulse/handshake/FIFO/multibit):
- Resets: name, type (POR/warm/soft/per-domain), sync/async assert/deassert, sequencing, reset values, what survives reset:
- Power: UPF revision, domains, states, legal transitions, isolation/retention/level-shift cells, always-on logic, wake sources:

## F. Functional behaviour
- Operating modes and mode transitions:
- Feature list (one line each, spec section ref):
- CSR map source (IP-XACT/SystemRDL/XML) + revision; side-effecting/volatile regs:
- Data-path transforms and golden/reference model availability:

## G. Error handling and recovery
- Error sources, detection, reporting (response codes, IRQ, status, logs), containment, recovery/clear procedure:
- Behaviour on illegal/unsupported stimulus (drop/error/UNPREDICTABLE — must be stated):

## H. Concurrency, ordering, performance
- Ordering domains/guarantees, arbitration policy, fairness bound, QoS:
- Buffer depths, credit counts, backpressure behaviour, overflow policy:
- Performance targets: latency (min/typ/max), throughput, under which workload + config:

## I. Security and privilege
- Secure/non-secure, privilege levels, firewalls, lock bits, debug-access policy, key/secret handling:

## J. Debug and observability
- Debug/trace ports, status/perf counters, DFT modes to exclude/include:

## K. Verification context
- Existing collateral: VIP (vendor/version), RAL, ref models, formal apps, previous vplan, known bugs/errata:
- Simulators + versions, formal/CDC/RDC/UPF tools, emulation target:
- Required levels: IP UVM / formal / subsystem / SoC C-driven / emulation:
- Coverage goals and exclusion policy; waiver approvers:
- Schedule milestones and signoff owner:

## L. Declared exclusions / out of scope (with rationale and approver)

---
## Requirement record (superset of 03-schema-verification-plan + 03-schema-traceability)
Fields marked * are NOT in the current uploaded schemas — see schema gap note.
```json
{
  "id": "REQ-<BLK>-<AREA>-<NNN>",
  "text": "",
  "priority": "P0|P1|P2",
  "source_ref*": "DOC-00x §x.y rev z",
  "origin*": "explicit|derived|assumed",
  "derived_from*": [],
  "category*": "functional|protocol|error|reset_recovery|concurrency|performance|security|low_power|debug|config",
  "level*": "IP|subsystem|SoC|formal|emulation",
  "configurations*": [],
  "methods": ["simulation|formal|emulation|inspection"],
  "stimulus*": "",
  "checks": [],
  "assertions": [],
  "coverage": [],
  "negative_tests*": [],
  "evidence": [],
  "expected_evidence*": "",
  "owner": "",
  "status": "open|implemented|passing|waived|blocked",
  "notes": ""
}
```
ID rules: never reuse or renumber; retired IDs stay with status=retired*; derived requirements cite parent IDs.

## Ambiguity/conflict register record
`AMB-NNN | doc refs | statement A | statement B/gap | impact | proposed resolution | decision owner | due | status`

## Assumption register record
`ASM-NNN | assumption | why needed | affected REQ IDs | risk if wrong | owner | expiry/validation trigger`
