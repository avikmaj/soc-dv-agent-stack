# SoC Integration & HW/SW Co-Verification — Initialization Baseline

**Status:** Proposed. No SoC collateral uploaded (spec, RTL, memory map, IP-XACT, UPF, boot ROM spec, firmware tree). All content is a parameterized plan. **Zero Observed execution results** — every status cell is "No evidence" until a run artifact conforming to `03-schema-regression-result.json` exists. Platform facts are Assumed placeholders.

**Date:** 2026-09-24

---

## 0. Selected skills

| Role | Skill | Applied to |
|---|---|---|
| Primary | soc-integration-verification | Scope, scenarios, regressions |
| Primary | hw-sw-coverification | C/FW architecture, sync, portability |
| Supporting | cdc-rdc-reset | Reset matrix |
| Supporting | low-power-upf | Power/clock rows |
| Supporting | noc-verification | Interconnect ordering/QoS/progress |
| Supporting | formal-sva | Connectivity, firewall, reset-sequencing properties |
| Supporting | coverage-closure | Signoff matrix |
| Supporting | emulation-readiness | Portability layer |
| Supporting | subsystem-verification | IP collateral qualification at entry gate |
| Deferred | signoff-audit | No evidence to audit yet |
| Deferred | spec-to-vplan | Runs once platform intake (§1) is answered |

---

## 1. Platform intake (blocking)

| # | Item | Artifact needed | Blocks |
|---|---|---|---|
| P1 | Hierarchy, IP list, instance counts | Top-level block diagram, IP-XACT/netlist hierarchy | Connectivity/address-map generation, instance parameterization |
| P2 | CPU clusters | ISA, core counts, cache levels, coherency protocol (CHI/ACE/proprietary), memory model (ARMv8/RVWMO/TSO) | Litmus set, barrier semantics, release flow |
| P3 | Accelerators / DMA masters | Coherent / non-coherent / IO-coherent; IOMMU/SMMU stages; stream IDs | DMA/IOMMU plan, CMO requirements |
| P4 | Interconnect/NoC | Topology, ordering domains, QoS classes, firewall/TZC placement | Ordering, progress, security plan |
| P5 | Memories | ROM/SRAM/DDR/LPDDR/HBM, ECC/parity, retention | Boot, error-injection, power rows |
| P6 | Boot chain | BootROM → BL1/BL2 → FW; media (QSPI/eMMC/UFS/USB/UART/PCIe); secure boot; fallback policy; strap/OTP | Boot matrix |
| P7 | Interrupt architecture | GIC/PLIC/AIA/proprietary; SPI/PPI/LPI/MSI; priority/preemption; wake sources | Interrupt plan |
| P8 | Security | EL/privilege model, TrustZone/PMP/WorldGuard, firewalls, debug auth, lifecycle states | Security/debug plan |
| P9 | Debug/trace | CoreSight or RISC-V debug; JTAG/SWD; ETM/trace sinks; cross-trigger | Debug plan |
| P10 | Clock/reset/power | Reset tree and types, PMU/SCP FW, power domains, UPF, DVFS points | Reset/power/CDC-RDC rows |
| P11 | Targets | Simulator(s)+version, emulator (Palladium/Veloce/ZeBu), FPGA prototype, silicon board | Portability layer, regression pyramid |
| P12 | Existing assets | Is soc_cuvm_suite v0.4 the reference harness, or different SoC/collateral? | Reuse vs fresh mailbox/test framework |

P12 is highest leverage: if soc_cuvm_suite is the base, §3 and §7 become a gap analysis rather than greenfield.

---

## 2. Feature & dependency inventory

Bring-up is a DAG; scenarios are not runnable until the predecessor layer has evidence.

| Layer | Capability | Depends on | First evidence gate |
|---|---|---|---|
| L0 | Clock gen, PLL lock, reset controller, strap/OTP sampling | — | Reset-release sequence assertions + smoke |
| L1 | BootROM fetch, ROM/SRAM, primary core reset vector | L0 | Boot-to-mailbox "alive" |
| L2 | Interconnect/NoC, address decode, default slave/DECERR, firewalls | L1 | Generated connectivity + address-map sweep |
| L3 | Interrupt controller, timers | L2 | Per-source routing sweep |
| L4 | Secondary core release, caches, MMU | L1–L3 | Multi-core barrier + litmus smoke |
| L5 | DMA, IOMMU, coherent IO | L2, L4 | Buffer-integrity + translation-fault tests |
| L6 | DDR controller, PHY model, ECC | L2 | Memory init + ECC inject |
| L7 | Power manager, clock gating, DVFS, retention | L0, L3, L4 | Power-state transition coverage |
| L8 | Debug/trace, authentication | L2, lifecycle | Debug-access × lifecycle matrix |
| L9 | Peripherals, boot media | L2, L3, L5 | Per-IP integration tests |
| L10 | E2E use cases, perf, stress | All | Scenario catalog (§8) |

---

## 3. HW/SW verification architecture (Proposed)

Separation of concerns: **test intent ≠ transport ≠ target**.

- **Test intent** — portable C tests see only `soc_api.h`: phase, sync, check, log, alloc.
- **HAL** — per-SoC register layer generated from IP-XACT; same source feeds UVM RAL (no CSR drift).
- **Transport** — mailbox + event channel in a dedicated non-cacheable, device-ordered region. Per-target backend:
  - Sim: UVM monitor snoops mailbox writes on the bus (not backdoor polling — avoids zero-time sampling races).
  - Emulation: SCE-MI/transactor pipe, batched.
  - FPGA/silicon: UART/JTAG/trace-sink drain.
- **UVM side**
  - `soc_sw_monitor` — decodes mailbox protocol.
  - `soc_vsqr` — coordinates TB stimulus (traffic, error injectors, power-event drivers) with SW phases.
  - `soc_eot_ctrl` — owns objection; drops only on SW completion token **and** TB scoreboard drain.
- **Loader** — backdoor ELF/hex preload in sim; real boot path or debug-port load on emu/Si; behind one `soc_loader_if` so tests cannot tell the difference.

### Mailbox contract (portability boundary — freeze early)

```c
typedef struct {
  volatile uint32_t magic;                  // 0x50C0DEAD once initialized by core0
  volatile uint32_t proto_ver;
  volatile uint32_t seed;                   // written by host/TB before release
  volatile uint32_t core_state[MAX_CORES];  // BOOTED/RUNNING/PASS/FAIL/TIMEOUT
  volatile uint32_t phase;                  // monotonic; TB waits on phase==N
  volatile uint32_t ev_wr_idx;              // event ring, single writer per core slot
  volatile uint32_t ev_ring[MAX_CORES][EV_DEPTH]; // {seq:8, id:12, argc:4, ...}
  volatile uint32_t result;                 // PASS=0x600D, FAIL=0xBAD0 | errcode
  volatile uint32_t checksum;               // over results/artifacts for silicon parity
} soc_mbox_t;
```

### Rules

- **Logging** — ID + args, never printf strings on target; host-side table resolves IDs. Keeps emulation throughput and silicon code size sane; logs diffable across targets.
- **Determinism** — seed injected via mailbox; each core derives `seed ^ core_id`. Simulator `+ntb_random_seed` and SW seed both recorded in the run record.
- **Timeouts (three-level)**
  1. Per-phase SW watchdog (cycle-based, target-scaled).
  2. TB-side phase timeout reporting stalled core and phase.
  3. Global `uvm_root` timeout, last resort only.
  Wall-clock timeouts are banned inside tests.
- **Completion** — PASS requires all of:
  1. All `core_state == PASS`.
  2. TB scoreboards drained.
  3. No UVM_ERROR/FATAL and no SVA failures.
  SW PASS alone is never sufficient.

---

## 4. Boot/reset matrix (Proposed)

### 4.1 Reset

| ID | Reset | Scope | Must preserve | Key checks | Targets |
|---|---|---|---|---|---|
| RST-01 | Cold/POR | All | Nothing (OTP excepted) | Release ordering, PLL-lock gating, strap latch window, X-free after release (X-prop mode) | Sim/Emu/Si |
| RST-02 | Warm (SW-requested) | Non-AON | Reset-reason reg, AON regs, retention SRAM | Reason-code correctness, AON isolation during reset, boot path taken | Sim/Emu/Si |
| RST-03 | Watchdog | Configurable | Reason reg, WDT count | Timeout→reset latency, pre-timeout IRQ, escalation to cold if unserviced twice | Sim/Emu |
| RST-04 | SW per-core | One core | Other cores running, coherency state | Snoop filter/directory cleanup, outstanding-txn quiesce, no hang on in-flight snoops | Sim (+formal assist) |
| RST-05 | Domain/subsystem | One PD/IP | Interconnect liveness | Bus quiesce/idle handshake, firewall reset values, RDC paths into live domains | Sim + RDC tool |
| RST-06 | Partial/peripheral | Single IP | Everything else | Pending IRQ/DMA cleanup, no stuck NoC credits | Sim |
| RST-07 | Reset during traffic | Any | Per rules above | Reset-abort in every VIP, no protocol violation on release, scoreboard flush policy | Sim |
| RST-08 | Back-to-back / glitch | All | — | Min pulse width, reset during reset-release window | Sim + formal |

### 4.2 Boot

| ID | Case | Expected outcome |
|---|---|---|
| BOOT-01 | Nominal, per boot medium | Reaches FW entry, `magic` set |
| BOOT-02 | Primary medium absent / corrupted image | Fallback to secondary medium within specified time |
| BOOT-03 | Auth fail (secure boot) | Halt or fallback per policy; no execution of unauthenticated code; error code latched |
| BOOT-04 | Rollback counter violation | Reject |
| BOOT-05 | All media fail | Recovery mode (UART/USB DFU), deterministic |
| BOOT-06 | Strap/OTP matrix | Each legal combination boots; illegal handled per spec |
| BOOT-07 | Warm-boot fast path | Skips cold init; retention restored |
| BOOT-08 | Watchdog fires during boot | Clean retry; boot-attempt counter increments |

BOOT-01..08 are fully spec-dependent (P6); pass/fail criteria cannot be written until the boot policy document exists.

---

## 5. Multi-core & coherency plan

### 5.1 Release & sync
- Core0 releases secondaries via power controller / release register; each secondary checks in.
- Barrier: sense-reversing, exclusive/atomic-based.
- Negative: secondary never checks in → TIMEOUT with core ID, not a hang.

### 5.2 Litmus set (per memory model, P2)
- Shapes: MP, SB, LB, IRIW, 2+2W, WRC — each with and without required fences / acquire-release.
- Pass = allowed-outcome consistency vs the architecture model. Collect outcome histograms over many iterations/seeds.
- Forbidden outcome observed → hard fail.
- Allowed-but-never-observed → coverage hole, not a pass signal.

### 5.3 Coherency stress
- False sharing on one line from N cores.
- Exclusive-monitor / CAS contention.
- Eviction under snoop.
- Directory / snoop-filter capacity overflow (back-invalidation).
- Stash/prefetch interaction.
- Clean/invalidate across the PoC.
- Non-coherent DMA with and without CMOs; the no-CMO case must detect staleness (proves the checker works).

### 5.4 Checker
- End-state memory checks alone are insufficient.
- Bus-level coherency scoreboard (CHI/ACE passive monitors) + per-line ordering checks.
- Formal on home-node protocol invariants where feasible (SWMR, no lost dirty data).

### 5.5 Interconnect ordering
- Same-ID ordering, Device vs Normal attributes, barrier/DSB propagation.
- Posted-write completion for MMIO-then-interrupt (classic silicon race).

---

## 6. Interrupt / DMA / security plan

| Area | Plan items |
|---|---|
| Interrupt | Generated per-source routing sweep (source → controller → target core); level/edge semantics; masking at source/controller/core; priority and preemption; affinity change while pending; spurious/lost IRQ under clock gating; wake-from-sleep IRQ; MSI/LPI ordering vs data (write data then MSI — data must be visible) |
| DMA | Descriptor chains, scatter-gather, alignment/length corners; abort mid-transfer; concurrent channels to shared destination; error-response propagation; E2E scoreboard with per-buffer CRC for emu/Si parity |
| IOMMU/SMMU | Stage 1/2 translation; faults (translation/permission/access-flag); stall vs terminate; TLB invalidation races with in-flight DMA; stream-ID isolation; fault IRQ reporting |
| MPU/firewall | Generated region × master × security-state access matrix; DECERR/SLVERR vs silent drop per spec; config lock bits; reprogramming with traffic in flight |
| Privilege | EL/mode transitions; trap to higher privilege; illegal-transition detection; secure/non-secure register banking |
| Debug | Access by lifecycle state (locked/unlocked/RMA) × auth state; halt/step/resume on each core while others run; debug access during reset and power-down; cross-trigger halt; trace start/stop; debug must not bypass firewalls unless spec says so |
| Error | ECC SEC (correct + log), DED (detect + escalate); bus error/timeout; parity; watchdog escalation chain; error-aggregator routing (IRQ/NMI/reset); containment — faulted IP must not hang the interconnect |
| Power/clock | All legal state transitions + illegal-request rejection; isolation/retention (UPF sim); DVFS under traffic; clock gating with pending IRQ; wake latency measured, not assumed |

**Formal candidates** (cheap to prove, expensive to cover in sim):
- Connectivity (generated from IP-XACT).
- Firewall decode (equivalence vs region table).
- Reset release sequencing.
- Interrupt routing mux.

---

## 7. Portable test abstraction

| Capability | Sim | Emulation | FPGA | Silicon | Rule |
|---|---|---|---|---|---|
| Backdoor load | Yes | Yes (memory preload) | Limited | No | Behind `soc_loader_if` |
| Force/deposit | Yes | Restricted | No | No | Error injection needs HW-visible injection register path for all targets |
| DPI into TB | Yes | Via transactor only | No | No | Tests never call DPI directly |
| Mailbox monitor | Bus snoop | Pipe | UART/JTAG | UART/JTAG/trace | Same protocol |
| Timebase | ns | Cycles | Cycles | Real time | Cycle-based timeouts, scaled per target |
| Checking | SW + scoreboards + SVA | SW + limited scoreboards | SW only | SW only | Every test has SW-only self-check mode; TB checks are additive |

**Portability gate:** a test is portable only if it passes in SW-only check mode. This is the criterion for promotion to emulation.

---

## 8. End-to-end scenario catalog (initial)

| ID | Scenario | Concurrency |
|---|---|---|
| E2E-01 | Cold boot → all cores up → barrier → DMA memcpy verified → orderly shutdown | Low |
| E2E-02 | Secure boot → NS OS handoff → NS attempts secure access → blocked and logged | Low |
| E2E-03 | Producer core fills buffer → DMA to accelerator → MSI to consumer core → consumer checks | Medium |
| E2E-04 | All cores: litmus + DMA stress + IRQ storm | High |
| E2E-05 | Enter low-power with DMA pending → deferred/completed per spec → IRQ wake → state intact | High |
| E2E-06 | ECC error injected mid-DMA → contained → SW recovery → resume | Medium |
| E2E-07 | Watchdog on hung core → warm reset → reason read → warm-boot fast path | Medium |
| E2E-08 | Debugger halts one core during coherent traffic, resumes, no deadlock | High |
| E2E-09 | DVFS change under full memory bandwidth | High |
| E2E-10 | Peripheral boot fallback with concurrent host PCIe/USB enumeration | Medium |
| E2E-PERF-* | Memory BW/latency, IRQ latency, DMA throughput, boot time — each with fixed workload, frequency config, measurement point | High |

---

## 9. Regression pyramid

| Tier | Content | Target | Cadence | Gate |
|---|---|---|---|---|
| L0 | Compile/elab, lint, connectivity formal, CSR reset/access (RAL) | Sim + formal | Every commit | Must pass |
| L1 | Boot smoke, per-core alive, 1 test per IP integration | Sim | Every commit | Must pass |
| L2 | Feature tests from §4–§6, deterministic seeds | Sim | Nightly | Must pass |
| L3 | CR stress, litmus sweeps, reset-during-traffic, error injection | Sim | Nightly, randomized seeds | Failures clustered and triaged |
| L4 | E2E catalog, long workloads, OS boot | Emulation | Weekly / per drop | Must pass for release |
| L5 | Perf, power-cycling soak, SW-only mode | FPGA / emulation | Per drop | Measured against targets |
| L6 | Portable subset re-run | Silicon | Bring-up | Correlation to sim results |

---

## 10. Evidence & signoff matrix

Current status of every row: **No evidence**.

| Area | Required evidence | Criterion (Proposed) | Status |
|---|---|---|---|
| Connectivity/map | Formal report, IP-XACT hash, tool/version | 100% proven, zero undetermined | No evidence |
| Reset/boot | Regression JSON for RST/BOOT; RDC report + waivers | All P0 passing; RDC waivers with owner/approver/expiry | No evidence |
| Multi-core/coherency | Litmus outcome histograms, coherency scoreboard logs | Zero forbidden outcomes; allowed-outcome coverage ≥ agreed threshold | No evidence |
| Interrupt | Routing sweep results, formal on mux | All sources × targets exercised | No evidence |
| DMA/IOMMU/security | Access-matrix results, fault logs | Full matrix covered, zero unintended access | No evidence |
| Debug | Lifecycle × auth results | Full matrix covered | No evidence |
| Power | UPF sim reports, transition coverage | All legal transitions covered, illegal rejected | No evidence |
| Errors | Injection coverage, containment results | All error classes injected and routed | No evidence |
| Portability | Same test IDs passing per target | Promoted set passing on sim and emulation | No evidence |
| Perf | Workload, config, measured numbers, run IDs | Meets spec targets, reproducible | No evidence |
| Coverage | Merged coverage mapped to requirement IDs; reviewed exclusions | Requirement closure (not headline %) | No evidence |

Each evidence item must carry: commit, configuration, tool/version, command, seed, run ID/timestamp, report path (per `01-evidence-contract.md`).

**Top-level verdict (PASS / CONDITIONAL / NOT READY):** computed only from this table. **Current: NOT READY** — no evidence exists.

---

## 11. Residual risks

1. Memory model and coherency protocol unknown — litmus set and coherency checker cannot be specified. Largest correctness risk.
2. Boot and security policies unknown — BOOT and debug matrices have no pass/fail oracle.
3. Emulation-safe error injection requires RTL injection hooks; without them, error-recovery coverage is sim-only.
4. Perf claims need a frozen workload and config; otherwise numbers are not comparable across targets.
5. RDC / dynamic-reset coverage depends on tool availability and waiver discipline.
6. FW owners writing tests outside `soc_api.h` silently degrades portability — needs a lint/CI check.

---

## 12. Human decisions required

- **P12:** base on soc_cuvm_suite, or greenfield?
- **Oracle ownership:** architecture spec vs reference model (ISS/Spike/FVP co-sim) for CPU and memory model.
- **Error-injection mechanism:** RTL hooks vs force-only (sim-only).
- **Target availability:** which emulator and FPGA platform, and when.
- **Signoff thresholds:** P0/P1 definitions, coverage thresholds, waiver approvers.

---

## 13. Next step

Answer P1–P12 or upload spec / IP-XACT / UPF / boot-policy collateral. Then run spec-to-vplan to produce a schema-conformant `verification-plan.json` with requirement IDs, and replace placeholders with platform facts.
