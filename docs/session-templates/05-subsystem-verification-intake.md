# Subsystem Integration Verification — Initialization Plan

Status: **Proposed**. Subsystem-agnostic skeleton; no subsystem collateral (spec, RTL, IP-XACT, UPF, IP list, IP-level evidence) has been provided. The only Observed inputs are the project control files. Per stop conditions ("unknown material configurations"), no IPs, maps, or versions are invented.

Date: 2026-09-24

---

## Selected skills

| Skill | Role |
|---|---|
| subsystem-verification | Primary |
| spec-to-vplan | Baseline + REQ-SS IDs (runs first once spec arrives) |
| uvm-env-architect | SS env composition from reused IP envs/VIP |
| ral-ipxact | SS reg block, multi-map, predictor policy |
| cdc-rdc-reset | Cross-IP crossings, reset release ordering |
| low-power-upf | Conditional on >1 power domain / retention |
| formal-sva | Connectivity, security no-leak, IRQ, deadlock properties |
| coverage-closure | Requirement-mapped closure |
| hw-sw-coverification | Firmware-driven scenarios |
| noc-verification | Conditional: only if fabric is a packetized NoC, not crossbar/bridges |
| signoff-audit | Excluded until evidence exists |

**Observed side finding:** the uploaded `02-skill-*` files would fail `04-script-validate.py` — they use `## Required inputs` / `## Evidence gate`, lack `## Checks`, and are well under the 1800-char floor. Contradicts "Initial production-ready foundation" in the 0.1.0 changelog.

---

## Material inputs needed (blocking concrete content)

1. Subsystem name, spec revision, top module/hierarchy, in/out boundary (explicit SoC-owned vs SS-owned).
2. IP inventory: instance, IP, version/commit, parameterization/defines, and IP-level evidence per instance (run ID, tool/version, coverage DB, waivers, commit).
3. IP-XACT/CSR source of truth, UPF, CDC/RDC setup (clock/reset intent).
4. Fabric type: AXI/ACE/CHI crossbar, NoC, APB/AHB bridges.
5. Security model: TrustZone NS, AxPROT/AxUSER propagation, firewalls/MPUs, debug access policy.
6. Firmware execution model: embedded core running C, host-driven C via DPI/mailbox, or both.
7. Simulator(s), formal tool (CC + property), coverage flow.
8. Performance targets (latency/BW per flow) and their source.

---

## 1. Integration inventory (template)

| Inst | IP | Commit/ver | Params/defines | IP-level evidence | Reusable collateral | Qualification |
|---|---|---|---|---|---|---|
| u_x | TBD | TBD | TBD | run ID, cov DB, waivers | env, agents, RAL, SVA, ref model | QUALIFIED / CONDITIONAL / UNQUALIFIED |

**Qualification rule (Proposed):** IP-level PASS carries forward only if RTL commit, parameter set, defines, and tool major version match the subsystem integration exactly. Any mismatch → CONDITIONAL; used parameter corners must be rerun at IP level or covered at SS level.

IP PASS never covers: tie-offs, integration-unique parameter corners, sideband semantics (QoS/USER/PROT/cache attributes), or behavior during another IP's reset/power-down.

**Unqualified-collateral register** (to populate): VIP lacking protocol-compliance evidence at the used revision; IP envs that cannot run passive; reference models with known gaps; generated RAL drifted from RTL; third-party IP without TB.

---

## 2. Connectivity and ownership matrix

| Class | Examples | Primary method | Owner | Rerun at next level |
|---|---|---|---|---|
| Data ports | AXI/AHB/APB mgr↔sub | Formal connectivity + passive VIP monitors | SS | SoC: boundary ports only |
| Sideband attributes | AxPROT/USER/QoS/CACHE, NS | Formal CC + scoreboard attribute check | SS | SoC |
| CSR access | Per-IP decode, aliases | RAL walk per map + address-map model | IP (field behavior) / SS (decode/map) | SoC global map |
| Interrupts | Source→aggregator→out | Formal CC + ss_irq_model_c | SS | SoC GIC/PLIC |
| Clocks/resets | Enables, dividers, reset trees | Formal CC + CDC/RDC tool | SS | SoC |
| Power control | PPU/P-/Q-channel, iso/ret enables | UPF-aware sim + static LP check | SS | SoC |
| Tie-offs/params | Straps, unused ports | Formal CC (constant propagation) + review | SS | — |
| Debug | APB-AP, CoreSight trace | Directed + formal | SS | SoC |
| DFT | Scan/MBIST | Out of scope (explicit exclusion) | DFT team | — |

**Ownership principle:**
- IP level owns protocol compliance and internal function.
- SS level owns decode/routing, cross-IP data paths, aggregation (IRQ/error), shared-resource arbitration, cross-IP ordering, reset/power sequencing interaction, and security attribute propagation.
- IP protocol checkers are reused passively (SVA via `bind`, VIP monitors passive). IP functional scoreboards are reused only where the internal boundary remains observable and unambiguous; otherwise they are replaced by end-to-end checks and the gap is recorded.

---

## 3. Subsystem verification architecture (Proposed)

```
ss_tb_top
 ├─ DUT (ss_top)  + bind: IP protocol SVA, ss_conn_sva, ss_sec_sva
 ├─ if arrays per boundary port, config_db keyed by instance path
 └─ uvm_test → ss_env_c
     ├─ m_cfg_h : ss_cfg_c (per-inst IP cfg handles, feature enables, map selection, perf knobs)
     ├─ m_<port>_agt_h[]     reused VIP, active at SS boundary, passive at internal taps
     ├─ m_<ip>_env_h[]       reused IP envs, is_active=UVM_PASSIVE, scoreboards retargeted/disabled per ownership matrix
     ├─ m_regmodel_h : ss_reg_block_c (IP-XACT generated; one uvm_reg_map per initiator view: host/secure/debug)
     │     explicit uvm_reg_predictor per map; auto-predict off
     ├─ m_addr_model_h : ss_addr_map_model_c  {initiator, addr, prot, user} → {target, local_addr} | DECERR | FW_BLOCK
     ├─ m_e2e_sb_h[]  : ss_flow_sb_c per flow class (CPU→mem, DMA mem→mem, periph→mem, ...)
     ├─ m_mem_model_h : byte-accurate shadow, in-flight window tracking
     ├─ m_irq_model_h : ss_irq_model_c (source→mask→pending→aggregate→output, level/edge, clear latency)
     ├─ m_rst_pwr_model_h : sequencing/state model from reset-controller and PPU monitors
     ├─ m_perf_mon_h  : per-flow latency histograms, BW per window, arb grant stats, occupancy taps
     ├─ m_vseqr_h     : ss_vsequencer_c (per-initiator seqr handles, reg seqr, fw mailbox seqr)
     └─ m_fw_if_h     : HW/SW layer (mailbox/semaphore in fixed SRAM region; C on core or DPI host)
```

**Design rules**
- Fully array-driven configuration: N instances of the same IP require no code change.
- Instance count and parameters come from a single generated `ss_cfg` source (IP-XACT) — no third hand-maintained copy of the map.
- Address-map model and RAL generated from the same source of truth; CI diffs generated output against RTL decode (formal or directed walk).
- Scoreboards consume monitor transactions only — never driver/sequence items.
- Firmware test intent separated from transport: the same C test runs host-driven early and on-core later.

---

## 4. End-to-end scenario catalog

| ID | Area | Scenario | Key checks | Coverage |
|---|---|---|---|---|
| SS-CONN-01 | Connectivity | Formal CC: all boundary, tie-off, IRQ, clock, reset, power nets | Proven / bounded at stated depth; covers reachable | Connection table 100% proven |
| SS-CFG-01 | Config | Every shipped legal param/strap set, smoke each | Elaboration + smoke | Param-set bins |
| SS-REG-01 | Register map | RAL hw_reset, bit_bash, mem_walk per map | Mirror == DUT; unmapped/illegal → spec response | Map × block × access policy |
| SS-REG-02 | Register map | Aliases, secure/non-secure views, debug view | No cross-view leakage | View × register |
| SS-IRQ-01 | Interrupts | All sources individual + simultaneous, masked/unmasked, level/edge | Causality, no lost/spurious IRQ, clear semantics | Source × mask × type × concurrent |
| SS-IRQ-02 | Interrupts | IRQ asserted during source reset/power-down | Spec behavior, no stuck output | Source × rst/pwr state |
| SS-RST-01 | Reset | Spec POR release order; each warm/soft domain in isolation | Sequencing model; no traffic accepted pre-ready | Domain × phase |
| SS-RST-02 | Reset | Domain reset with outstanding traffic from other domains | Spec response (error/complete), no hang/corruption | Domain × outstanding depth |
| SS-XING-01 | CDC/RDC | Clock ratio sweep incl. async jitter on all crossings | Integrity through sync/FIFO crossings | Ratio × path |
| SS-PWR-01 | Power | All legal power-state transitions, idle and under traffic | Iso/retention/restore, quiesce handshake, X-free outputs | State × transition × traffic |
| SS-PWR-02 | Power | Illegal/aborted transitions (deny/timeout paths) | Spec denial/recovery | Illegal-transition bins |
| SS-ARB-01 | Arbitration | All initiators saturating same target | Fairness bound, QoS respected, no starvation beyond spec | Contenders × QoS × burst |
| SS-BP-01 | Backpressure | Random + worst-case READY/credit throttling at every sink | No loss/dup/deadlock; bounded completion | Throttle profile × port |
| SS-E2E-01 | Data integrity | Mixed-flow concurrent traffic, overlapping addresses | Shadow memory match, per-ID order, RAW/WAW at ordering point | Flow × size × alignment × overlap |
| SS-DMA-01 | DMA | Descriptor chains, SG, aborts, reprogram during activity | Descriptor-predicted data, completion IRQ causality | Chain len × abort point |
| SS-ERR-01 | Errors | SLVERR/DECERR injection per target; error IRQ/status aggregation | Containment, escalation, recovery | Error src × resp × escalation path |
| SS-SEC-01 | Security | NS access to secure regions/regs; firewall reprogram under traffic | Block + response + log/IRQ; no leak, no write effect | Initiator × prot × region × fw config |
| SS-SEC-02 | Privilege | Unprivileged/debug access policy | Per-spec policy | Priv × target |
| SS-PERF-01 | Performance | Reference workloads per flow | Latency/BW vs spec targets | Histogram bins |
| SS-FW-01 | Firmware | Boot/init, driver-style bring-up, polling vs IRQ completion | FW-visible status coherent with HW model | FW path bins |
| SS-FW-02 | Firmware | FW + DMA + external initiator concurrency | Semaphore/mailbox correctness, no lost updates | Contention bins |

---

## 5. Scoreboard / checker architecture

| Layer | Mechanism | Detects |
|---|---|---|
| L0 protocol | Bound IP/VIP SVA + passive monitors at every internal tap | Protocol violations localized to offending interface |
| L1 structure | Formal connectivity, constant/tie-off checks | Miswiring, swapped buses, wrong IRQ index, dead power enables |
| L2 routing | ss_addr_map_model_c comparing observed ingress→egress | Misrouting, wrong local address, missing DECERR, firewall bypass |
| L3 end-to-end | Flow scoreboards keyed {initiator, ID, stream} | Loss, duplication, corruption, ordering violations |
| L4 system invariants | SVA / assertion monitors | Credit conservation, outstanding ≤ limit, IRQ causality, security no-leak (secure data never on NS response), forward-progress watchdogs |
| L5 performance | m_perf_mon_h vs spec thresholds | Bottlenecks, fairness bounds, starvation |

- Ordering semantics encoded per protocol, not generically. AXI: same-ID ordered; different-ID unordered; write-response-before-dependent-read only where the spec/topology guarantees it.
- Memory model tracks in-flight windows; a read overlapping an uncommitted write accepts the set of legal values — avoids false fails without masking real corruption.

---

## 6. Negative and fault-injection plan

| Fault | Injection | Expected | Owner |
|---|---|---|---|
| Target error response | VIP responder mode / error sequence | Propagated resp, status/IRQ, no side effects | SS |
| Decode hole / illegal address | Directed + random unmapped | DECERR per spec | SS |
| Security violation | NS/unprivileged initiator | Blocked, logged, IRQ per spec | SS |
| Reset mid-transaction | Virtual seq asserts domain reset at random phases | Spec-defined, no hang | SS |
| Power-down under traffic | PPU request under load | Denied or quiesced correctly | SS |
| Watchdog/timeout | Target never responds | Timeout detection, recovery | SS |
| Parity/ECC | Force/deposit on protected arrays (sim only — emulation-incompatible) | Correction/detection/escalation | IP (detect) / SS (escalate) |
| Illegal register sequence | FW programs out of order / during busy | Spec behavior, no lockup | SS + FW |
| X injection | Uninitialized non-reset flops, isolated outputs | No X on functional outputs | SS |

Injected faults are announced to checkers via an analysis port so the expected outcome is predicted rather than suppressed; injection must not corrupt scoreboard reference state.

---

## 7. Performance plan

- **Workloads:** per-flow reference traffic (sizes, burst mix, ID spread, locality, concurrency) sourced from architecture — not invented.
- **Metrics:** per-flow latency (min/mean/p99/max), sustained BW per port, arbitration grant share, buffer/credit occupancy, stall attribution.
- **Observability:** monitor timestamps at ingress/egress plus internal taps at arbiters/FIFOs via passive binds.
- **Reproducibility:** every perf claim carries commit, config, seed, workload ID, tool/version, report path.
- **Pass criteria:** only from spec targets. Without targets, output is characterization, labeled Unverified against intent.

---

## 8. Coverage and traceability matrix (template)

| REQ ID | Text | Pri | Methods | Checks | Coverage | Status | Evidence |
|---|---|---|---|---|---|---|---|
| REQ-SS-CONN-001 | TBD (from spec) | P0 | formal | ss_conn | conn table | open | — |
| REQ-SS-SEC-001 | TBD | P0 | sim + formal | L2, L4 no-leak | init×prot×region | open | — |

Key crosses:
- initiator × target × prot × resp
- irq_src × mask × rst/pwr_state
- pwr_transition × outstanding_depth
- contenders × QoS × burst_len
- flow × addr_overlap × alignment

Hole classification: stimulus / observability / checker / model / unreachable / configuration / exclusion. All exclusions/waivers go through the waiver schema with owner, approver, expiry.

---

## 9. Regression tiers

| Tier | Content | Trigger |
|---|---|---|
| T0 smoke | Formal CC, RAL hw_reset, one transaction per initiator→target | Every commit |
| T1 feature | Per-scenario constrained-random, modest seeds | Daily |
| T2 concurrency/stress | Mixed flows, throttling, arbitration saturation | Nightly |
| T3 error/fault | Negative plan | Nightly |
| T4 reset/power | UPF-aware sim, reset sequencing | Nightly (license-bound) |
| T5 performance | Reference workloads, fixed seeds | Weekly / on fabric change |
| T6 firmware | C-driven bring-up and concurrency | Weekly / on FW drop |

Seed counts and runtimes to be set once simulation throughput is measured.

---

## 10. Entry / exit criteria

**Entry**
- Spec baselined with revision.
- IP inventory with commits; every IP QUALIFIED or CONDITIONAL with an explicit rerun plan.
- IP-XACT and UPF frozen for the milestone.
- Connectivity table generated.
- VIP revisions pinned.
- SS env compiles and passes T0.

**Exit (objective)**
- Every P0/P1 REQ-SS has current passing evidence (commit, config, seed, run ID).
- Formal CC proven, or bounded at an agreed depth with reachable covers.
- CDC/RDC clean or covered by approved, unexpired waivers.
- Coverage holes classified; only reviewed exclusions remain.
- No open P0/P1 bugs; intermittents root-caused.
- Performance targets met on reproducible workloads.
- SoC reuse package delivered: passive-capable env, RAL, SVA binds, scoreboards, C tests.

Verdict (PASS / CONDITIONAL / NOT READY) issued only via signoff-audit.

---

## 11. SoC reuse requirements

- All SS env components run passive with no dependency on SS-boundary driving.
- RAL block instantiable into the SoC map at an offset.
- Address-map model parameterized by base address.
- SVA delivered as bind files.
- C tests use a HAL separating register access from transport.
- No hard-coded hierarchical paths — everything via config_db and the cfg object.

---

## 12. Residual risks and human decisions

**Risks (Assumed until inputs arrive)**
- IP-level evidence at a different parameterization than the SS uses.
- RAL / IP-XACT / RTL drift.
- Underspecified ordering guarantees in the fabric spec.
- Missing performance targets.
- Firmware unavailable before late RTL.
- UPF-aware simulation license/throughput limits.

**Human decisions needed**
- Which IP scoreboards are retained at SS level vs replaced by end-to-end checks.
- Formal CC bound for any unproven nets.
- Map source of truth: IP-XACT, SystemRDL, or spreadsheet.
- Performance target ownership.
- Security verification scope: formal no-leak properties or sim-only coverage.
- SS/SoC boundary for debug and DFT.

---

## Next steps

1. Provide subsystem spec revision, IP inventory with commits and IP-level run evidence, IP-XACT, UPF, and fabric type.
2. Run spec-to-vplan to extract REQ-SS IDs and populate `03-template-verification-plan.json` and traceability records.
3. Bind the architecture to the real IP list: concrete `ss_cfg_c`, reg block composition, flow scoreboard set.
4. Decide whether to fix the skill-file section headers so `validate.py` passes.
