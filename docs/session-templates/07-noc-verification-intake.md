# NoC / Fabric / Interconnect Verification Framework

Status: **Proposed** (design-independent; no design collateral attached yet)
Date: 2026-09-24
Evidence class: nothing below is Observed. No topology or interface behavior has been invented; design-specific artifacts are produced after intake.

---

## 1. Scope and selected skills

**Primary skill:** noc-verification

**Supporting skills** (added only when their domain is in scope):

| Skill | Applies when |
|---|---|
| formal-sva | Routing, credit, and ordering invariants; deadlock arguments |
| coverage-closure | Hole classification against requirement IDs |
| subsystem-verification | The NoC runs with real IP endpoints |
| soc-integration-verification | Firmware-driven traffic, or interrupt/DMA paths through the fabric |
| cdc-rdc-reset | Async bridges; per-domain reset of NIs and routers |
| low-power-upf | Switchable fabric domains, isolation, link quiesce |
| spec-to-vplan | The spec baseline is not frozen (this skill runs first) |
| signoff-audit | Evidence exists (this skill runs last) |

---

## 2. Intake (material questions only)

1. **Target.**
   - Is this the existing `noc_vip`, or a specific fabric DUT?
   - Is the fabric generator-produced? If so, which config or IP-XACT file is the source of truth?
   - Is it coherent (CHI/ACE) or non-coherent (AXI/AHB/APB)?
2. **Topology source.** A spec, generator output, or an RTL-extracted netlist. Routing is never derived from RTL comments.
3. **Protocols and revisions** at every NI:
   - initiator side;
   - target side;
   - internal packet/flit format.
4. **Ordering contract.**
   - Which fields define an ordering domain: ID, address, or QoS.
   - Whether reordering is permitted across targets or across VCs.
   - Whether responses may interleave.
5. **Routing and flow control.**
   - Routing algorithm: static tables, XY, or adaptive.
   - VC or traffic-class count, and the escape-VC scheme.
   - Per-hop flow control: credit or valid/ready.
6. **Performance targets.**
   - Latency and bandwidth per flow.
   - Fairness bound.
   - The source document for each target.
7. **Tools.**
   - Simulator and version.
   - Formal tool availability. This decides whether the deadlock and credit invariants get proofs or only simulation checks.
   - Emulation availability for saturation runs.

### Baseline items to establish before verification

- Topology.
- Nodes: initiators, targets, routers, switches, bridges.
- Protocols and their revisions.
- Address and routing maps.
- VCs, traffic classes, priorities, and QoS.
- Ordering domains and the reordering each one permits.
- Buffer, credit, and backpressure architecture.
- Width, clock, and protocol conversion points.
- Security and firewall rules.
- Performance and fairness requirements.

---

## 3. Topology and feature inventory

The inventory is a machine-readable graph generated from the source of truth. It is never hand-written.

- **Nodes.** NI-I, NI-T, router, switch, bridge, firewall, CDC/width converter. Each node records its clock domain and reset domain.
- **Links.** Each link records width, VCs, credit depth, and pipeline stages.
- **Routes.** A mapping from `(src, dst, addr_range, vc)` to a path.

This single artifact feeds three consumers, so there is no second copy that can drift:
- the scoreboard route model;
- the coverage bins;
- the static deadlock analysis.

---

## 4. Ordering-domain matrix (template)

**Rows (ordering key):**
- same ID;
- same target;
- same or overlapping address;
- same VC;
- WAR and RAW within the same ID.

**Columns (scope):**
- same target;
- different target;
- same VC;
- different VC.

**Cell values:**

| Value | Meaning |
|---|---|
| MUST-ORDER | Reordering is a failure |
| MAY-REORDER | The checker tolerates reordering |
| UNSPECIFIED | Escalated as a spec gap; never defaulted |

---

## 5. Traffic-model catalog

Traffic models are parameterized sequences, not directed tests. Each model is a configuration object with:
- injection rate;
- source and destination distributions;
- packet size distribution;
- ID/QoS policy;
- seed.

The same objects are reused for performance runs.

| Model | Purpose |
|---|---|
| Uniform random | Baseline reachability and load |
| Hotspot / incast (N:1) | Target contention, arbitration fairness |
| Transpose, bit-complement, tornado | Mesh/torus link stress |
| Bursty on/off | Buffer occupancy extremes |
| Request/response coupled | Protocol-level dependency, response VC pressure |
| Ordering stress (same ID, overlapping address) | Ordering matrix coverage |
| Mixed-QoS priority | QoS arbitration, priority inversion |
| Long-packet HoL stressors | Head-of-line blocking |
| Saturation ramp | Latency vs offered-load curve, finding the knee |

---

## 6. End-to-end scoreboard architecture

- **Monitors.** Passive monitors sit at every NI boundary. Monitors are authoritative; the scoreboard never taps driver intent.
- **Transaction tracker.**
  - Keyed by `(src_ni, id, seq_tag)`.
  - Predicts the destination from the address map plus the route model.
  - Applies expected transforms: width conversion, protocol conversion, and the firewall decision.
- **Ordering check.** Per-domain queues are checked against the ordering matrix. There is no global FIFO.
- **Response matching.**
  - The ID/tag of every response is correct.
  - No orphan responses.
  - No duplicate responses.
  - Every request gets a response unless it was legally error-terminated.
- **Conservation.** A check runs mid-test at quiescent points, plus an end-of-test drain check.
- **Failures detected:**
  - loss;
  - duplication;
  - corruption;
  - misrouting;
  - illegal reordering;
  - response mismatch;
  - outstanding-transaction leaks.

---

## 7. Invariant and assertion plan

Each invariant is a simulation SVA per link or NI. The same invariant is a formal target at router or NI granularity.

| ID | Invariant |
|---|---|
| INV-CONS | injected = delivered + in-flight + error-terminated, per flow |
| INV-CRED | Credit count stays in [0, depth]; credit return ≤ flits consumed |
| INV-VC | No flit interleave across packets within a VC unless allowed; head/tail framing is legal |
| INV-HOLD | Payload is stable while `valid && !ready`, at every valid/ready hop |
| INV-ROUTE | Output port = `route_table(dst, vc)` at every hop |
| INV-FW | A denied access never reaches its target; the error response is generated at the defined point |
| INV-PROG | Every buffered flit advances within N cycles when downstream credit is available (liveness; bounded in simulation) |

The formal review covers:
- assumptions checked for overconstraint;
- vacuity, verified with cover properties;
- reachability of each cover;
- undetermined results reported as undetermined, never as proofs.

---

## 8. QoS, fairness, and deadlock plan

### Static analysis
- Build the channel dependency graph (CDG) from the route tables plus the VC allocation.
- Prove the CDG acyclic, or show that escape VCs break every cycle.
- Implement this as a script over the topology artifact, so the result is deterministic evidence.
- Analyze protocol-level deadlock separately from the CDG: request/response dependency and request/response VC separation.

### Dynamic analysis
- Grant-wait distributions per arbiter.
- Starvation bounded by the spec limit.
- Forward-progress watchdogs using per-VC age counters.
- Livelock detection for adaptive routing: hop-count and misroute limits.
- QoS priority-inversion scenarios.
- Congestion and head-of-line blocking measured under hotspot and long-packet models.

---

## 9. Error-injection plan

Each injected error has:
- one expected containment point;
- one expected response code.

Pass criteria for every injection:
- no hang;
- no corruption of any neighbor flow.

| Category | Injection |
|---|---|
| Decode | Unmapped address, illegal destination |
| Security | Firewall or privilege violation |
| Target | SLVERR/DECERR, target timeout |
| Integrity | Flit parity/ECC error (if implemented) |
| Link | Link drop mid-packet |
| Reset | Per-domain reset with traffic in flight; bridge quiesce/unquiesce |

---

## 10. Performance methodology

A performance claim is **Unverified** unless every item below is present:

- configuration hash;
- seed set of at least N seeds;
- warm-up interval (excluded from measurement);
- fixed measurement window;
- per-flow statistics: mean, p50, p99, and max latency; throughput; link utilization;
- latency vs offered-load curve up to the saturation knee;
- confidence intervals across seeds;
- a regression result JSON (per `03-schema-regression-result.json`) plus a performance report path.

---

## 11. Coverage and traceability

### Requirement ID scheme
`NOC-{REACH, DECODE, INTEG, ORD, RSP, CRED, BUF, ARB, HOL, DLK, CONV, RST, SEC, ERR, PERF}-nnn`

IDs are mapped with `03-schema-traceability.json`.

### Coverage model
- Route table: `src × dst × vc`.
- Every cell of the ordering matrix.
- Credit occupancy: 0, 1, max-1, max.
- Arbiter contention depth; QoS inversion scenarios.
- Cross of error type × containment point.
- Reset asserted during each packet phase.
- Width, clock, and protocol conversion corners.

### Hole classification
Holes are classified per coverage-closure:
- stimulus;
- observability;
- checker;
- model;
- unreachable;
- configuration;
- exclusion.

Exclusions and waivers are signoff artifacts and follow `03-schema-waiver.json`: evidence, owner, approver, and expiry are all required.

### Verification checklist (15 areas)
1. Reachability and routing correctness
2. Illegal destination and decode behavior
3. Loss, duplication, corruption, misrouting
4. Ordering and permitted reordering
5. Response matching and outstanding transactions
6. Backpressure and credit accounting
7. Buffer overflow, underflow, and reservation
8. Arbitration, QoS, fairness, and bounded starvation
9. Congestion and head-of-line blocking
10. Deadlock, livelock, and forward progress
11. Width, clock, and protocol conversion
12. Reset, link interruption, and recovery
13. Security, privilege, and isolation
14. Error injection and containment
15. Latency, throughput, utilization, and saturation

---

## 12. Signoff criteria

| Verdict | Criteria |
|---|---|
| PASS | All P0/P1 requirements pass on the current commit and config; CDG proven acyclic; no open INV failures; every waiver has owner, approver, and expiry; performance targets met with the statistics in §10 |
| CONDITIONAL | Residual items remain, each with documented risk acceptance |
| NOT READY | Anything else |

---

## 13. Residual gaps and observed issues

**Observed.** The uploaded `02-skill-*` files would fail the stack's own `validate.py`:
- they use `## Required inputs` where the validator expects `## Inputs`;
- they use `## Evidence gate` where the validator expects `## Evidence Gate`;
- they have no `## Checks` section;
- each is below the 1800-character minimum.

Source: `02-skill-noc-verification.md` compared with `04-script-validate.py.txt`. This does not block the NoC work, but CI on that repository will stay red until the skills or the validator are reconciled.

**Pending on intake:**
- all design-specific content;
- the populated inventory;
- the filled ordering matrix;
- the performance targets.

---

## 14. Next steps

1. Answer the intake items in §2.
2. Attach the topology/config source of truth and the ordering specification.
3. Deliverables once those arrive:
   - populated topology inventory;
   - filled ordering-domain matrix;
   - first-cut vplan JSON per `03-schema-verification-plan.json`.
4. If the target is `noc_vip`, the work continues from its existing state and open GAPs instead of starting fresh.
