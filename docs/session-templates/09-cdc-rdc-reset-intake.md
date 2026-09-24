# CDC / RDC / Reset-Sequencing Analysis — Workspace Initialization

- Date: 2026-09-24
- Primary skill: cdc-rdc-reset (v0.1.0)
- Supporting skills: rtl-design-review, formal-sva, low-power-upf, subsystem-verification, soc-integration-verification (invoked only where applicable)
- Evidence state: **No RTL, SDC, UPF, CDC setup, or reports provided. Nothing below is Observed.** Inventory rows are schema templates; risks are class-level priors (Derived only once mapped to real crossings).

> A clean structural CDC/RDC report is necessary, not sufficient. It is never treated as proof of functional coherency.

---

## 1. Intake required (blocking)

| # | Input | Why |
|---|---|---|
| I1 | RTL filelist, top, git commit, defines/parameters per configuration | Structural analysis is only meaningful per elaborated config |
| I2 | SDC: create_clock / create_generated_clock / clock groups (async, exclusive, physically exclusive), set_case_analysis per mode | Most false-clean CDC results come from mis-grouped or missing generated clocks |
| I3 | Clock/reset architecture spec: sources, dividers/muxes, ICGs, reset controller FSM, ordering requirements | Intent — tool output cannot supply it |
| I4 | Mode list: functional, low-power, scan shift/capture, MBIST, JTAG/debug, boot | Each mode is a separate analysis configuration |
| I5 | UPF: domains, supply states, isolation, retention, level shifters, PST | Power-domain crossings, reset/power interaction |
| I6 | CDC/RDC tool + version + setup (constraint/directive files), synchronizer cell library, custom-sync definitions | Tool provenance |
| I7 | Existing CDC/RDC reports, waiver/exclusion files, approvers | Waiver audit |
| I8 | Known silicon/emulation escapes, prior CDC bugs on this IP family | Risk prioritization |

Material clarifications:
1. Analysis unit: IP, subsystem, or full SoC?
2. Tool: Questa CDC/RDC, SpyGlass CDC, Meridian CDC/RDC, or JasperGold CDC/RDC?
3. Is metastability-injection simulation available in the approved environment?

---

## 2. Clock / reset / domain inventory (schema — to be populated)

### 2.1 Clocks

| Clk ID | Name/port | Source (PLL/pad/div/mux) | Freq range | Generated from | Group (async/sync/exclusive) | Gated by (ICG, enable domain) | Stop/start conditions | Modes active | Status |
|---|---|---|---|---|---|---|---|---|---|
| CLK-xx | | | | | | | | | Unverified |

### 2.2 Resets

| Rst ID | Name | Source (POR/pad/SW/WDT/debug/PMU) | Polarity | Assert (async/sync) | Deassert sync'd to | Sync depth | Domains reached | Parent/child | Status |
|---|---|---|---|---|---|---|---|---|---|
| RST-xx | | | | | | | | | Unverified |

### 2.3 Domains

| Dom ID | Clock | Reset | Power domain | Retention? | Isolation clamp value | Owner |
|---|---|---|---|---|---|---|
| DOM-xx | | | | | | |

### 2.4 Clock gating / stop-start

| ICG / mux ID | Clock | Enable source domain | Enable sync'd? | Glitch-free mux? | Stop/start protocol | Status |
|---|---|---|---|---|---|---|

### 2.5 Existing synchronization structures

| Sync ID | Type (2FF/pulse/toggle/handshake/FIFO/gray/custom) | Src dom | Dst dom | Recognized by tool? | Waiver ref | Status |
|---|---|---|---|---|---|---|

---

## 3. Crossing-classification matrix

| Class | Required structure | Functional hazard (not proven by structural tool) | Primary check |
|---|---|---|---|
| Static config | Quasi-static attribute + documented change protocol | Changed while destination active | SVA: stable while dst enabled; protocol verified in sim |
| Single-bit level | ≥2-FF synchronizer, no pre-sync combinational logic | Glitch through combo logic, fanout pre-sync | Structural + netlist glitch review |
| Pulse / event | Toggle or pulse synchronizer | Loss when src pulses closer than ~2–3 dst periods; duplication on re-toggle | Src min-spacing SVA; scoreboard event count |
| Toggle | Toggle flop → sync → XOR edge detect | Reset mismatch → phantom event | Reset-alignment SVA; reset-mid-traffic test |
| Handshake (2/4-phase) | Sync'd req/ack, data held | Data change before ack; early req drop | Data/req stability SVA; formal protocol |
| Multi-bit data | Qualified by sync'd enable or mux-recirculation | Incoherent bit capture | SVA: dst capture only on qualifier; formal coherency |
| Gray counter | Registered gray, 1-bit change per src clock | Combinational gray; multi-bit change; non-power-of-2 wrap | `$onehot0` SVA + structural registered-output check |
| Async FIFO | Gray pointers sync'd; full/empty from sync'd pointers | One-sided reset/flush; pessimism deadlock; overflow | SVA + formal + ratio-sweep stress sim |
| Reconvergent control | Merge after sync only through coherent encoding | Divergent sync latency → illegal combined state | Metastability-injection sim; redesign |
| Reset crossing (RDC) | Isolation / qualification / reset ordering | Async assert in domain A corrupts non-reset domain-B flop | RDC tool + SVA + reset-sequence sim |
| Test / debug | Mode-qualified; set_case_analysis | Functional clocks mixed in scan; TCK→functional unsynchronized | Separate per-mode run; DFT review |

Per-crossing record fields (map to 03-schema-traceability.json):

`XID, src_dom, dst_dom, signal(s), width, class, sync_struct, tool_rule_id, tool_status, functional_check, evidence, owner, status`

---

## 4. High-risk crossing list (a-priori, Derived from class hazards)

| Rank | Pattern | Why |
|---|---|---|
| H1 | Reconvergence of independently synchronized control bits | Structurally clean, functionally broken |
| H2 | Multi-bit buses qualified by an enable that is not truly held | Most common "clean report, broken silicon" case |
| H3 | Async FIFO with non-bilateral reset/flush | Pointer skew after partial reset → phantom data / deadlock |
| H4 | RDC from SW/WDT resets resetting a sub-domain while neighbours run | Tools often configured with POR only |
| H5 | Fast→slow pulse sync across full ratio range | Loss invisible at nominal frequency |
| H6 | Mux-switched clocks (glitch-free mux) and ICG enables sourced cross-domain | Glitch; per-mode domain definition |
| H7 | Isolation enable / power-good into always-on logic | Unsynchronized PMU control; clamp-vs-reset race |
| H8 | Debug/JTAG → functional registers; APB → core CSR "static" config | Frequently waived as static without protocol evidence |

---

## 5. Structural and functional verification plan

| Step | Activity | Output |
|---|---|---|
| S1 | Constraint audit: all generated clocks declared, clock groups justified, per-mode case analysis | Constraint review record; unresolved / inferred-clock count = 0 |
| S2 | Structural CDC per mode (functional, each LP state, scan, debug) | Report by rule: violations / cautions / evaluations; zero "not analyzed" |
| S3 | Structural RDC with all reset sources modelled (not just POR) | RDC path report by reset pair |
| S4 | Synchronizer-library and custom-sync recognition review | No crossing accepted solely via blackbox/directive without review |
| S5 | Protocol SVA bound to every handshake, FIFO, pulse, and qualified bus | Assertion list + fire/vacuity data from sim |
| S6 | Formal on FIFO / handshake / gray blocks; prove coherency assumptions | Proven / bounded / undetermined per property with depth justification |
| S7 | Metastability-injection sim on regression subset (Questa CDC-FX, Meridian MI, or approved equivalent) | Per-seed pass/fail with injection enabled |
| S8 | Clock-ratio sweep (min/typ/max per ratio, extreme skew) | Scoreboard loss/duplication counts |
| S9 | Reset-sequence sims per §7; reset mid-traffic at random points | Scoreboard continuity + X-free-after-release checks |
| S10 | UPF-aware power-state transition sims: isolation, retention restore, reset interaction | PST arc coverage |
| S11 | Waiver audit per §8; rerun and baseline delta reconciliation | Signed waiver register |

---

## 6. Assertion / formal recommendations (Proposed — not compiled)

```systemverilog
// Pulse sync: source-side minimum gap (MIN_GAP derived from worst-case dst/src period ratio)
property p_pulse_min_gap(logic clk, rst_n, pulse);
  @(posedge clk) disable iff (!rst_n) pulse |=> (!pulse)[*MIN_GAP];
endproperty

// 4-phase handshake: req held and data stable until synchronized ack
property p_hs_hold(logic clk, rst_n, req, ack_s, logic [W-1:0] data);
  @(posedge clk) disable iff (!rst_n) (req && !ack_s) |=> (req && $stable(data));
endproperty

// Gray pointer: at most one bit changes per source clock
property p_gray_onehot(logic clk, rst_n, logic [AW:0] gptr);
  @(posedge clk) disable iff (!rst_n) $onehot0(gptr ^ $past(gptr));
endproperty

// Qualified multi-bit capture: dst register updates only on synchronized enable
property p_qual_capture(logic clk, rst_n, en_sync, logic [W-1:0] q);
  @(posedge clk) disable iff (!rst_n) !en_sync |=> $stable(q);
endproperty

// RDC qualification: dst must not capture while src domain is (synchronized) in reset
property p_rdc_block(logic clk, dst_rst_n, src_in_rst_s, capture_en);
  @(posedge clk) disable iff (!dst_rst_n) src_in_rst_s |-> !capture_en;
endproperty

// Reset synchronizer release: synced reset rises only after raw reset high for SYNC_DEPTH clocks
property p_rst_release(logic clk, raw_rst_n, sync_rst_n);
  @(posedge clk) $rose(sync_rst_n) |-> $past(raw_rst_n, SYNC_DEPTH);
endproperty

// Async FIFO protection
property p_no_ovf(logic clk, rst_n, wr_en, full);
  @(posedge clk) disable iff (!rst_n) wr_en |-> !full;
endproperty
property p_no_unf(logic clk, rst_n, rd_en, empty);
  @(posedge clk) disable iff (!rst_n) rd_en |-> !empty;
endproperty
```

Rules:
- Pair every assertion with a cover (e.g. `cover property (req && !ack_s ##[1:$] ack_s)`); record vacuity per the evidence contract.
- Formal on FIFO/handshake/gray uses abstracted, free-running independent clocks — not a fixed assumed ratio. Bounded results are reported as bounded, with depth rationale.
- Any `assume` on source behaviour (e.g. pulse spacing) becomes a source-side assertion that must be proven or covered at integration level (overconstraint review).
- Reconvergence is not SVA-provable: resolve with metastability-injection sim plus encoding redesign, not a waiver.
- Undetermined formal results are not proofs.

---

## 7. Reset-sequence matrix (template)

| Seq ID | Trigger | Resets asserted (order) | Clocks required during assert/release | Resets held / not held | Release order + sync | Isolation / PD state | Expected post-release state | Check | Status |
|---|---|---|---|---|---|---|---|---|---|
| RS-POR | Power-on | all | ref only / PLL-lock gating | — | per spec | all on | CSR resets, FIFOs empty | SVA + sim | Unverified |
| RS-WARM | SW / WDT | | | AON, debug | | | | | Unverified |
| RS-DOMAIN | Per-IP soft reset | single domain | | neighbours running | | | no neighbour corruption (RDC) | | Unverified |
| RS-DBG | Debug / JTAG reset | | | functional | | | | | Unverified |
| RS-PWR | Power-down / up | | clocks stopped | | retention restore before release | iso on→off ordering | | | Unverified |
| RS-MID | Reset mid-transaction (per interface) | | | | | | no phantom / lost events after release | scoreboard | Unverified |

---

## 8. Waiver audit (per 03-schema-waiver.json)

Fields: `id, category, target, rationale, evidence, owner, approver, expiry, status`

Reject / hold a waiver if any of:
- Owner, approver, or expiry missing.
- Rationale is "static", "false path", or "don't care" without a cited protocol guaranteeing it.
- No evidence path (SVA, formal result, or sim artifact).
- Wildcard, module-level, or hierarchy-level match instead of a specific crossing.
- Source commit older than the current analysis commit without re-validation.

Classification of surviving waivers:
- True-by-construction
- Protocol-guaranteed (evidence required)
- Mode-exclusive (case analysis required)
- Accepted-risk (human decision)

Waiver/exclusion edits are gated by explicit approval; changes are proposed, not applied.

---

## 9. Required tool evidence (per evidence contract)

Every structural run:
- commit, configuration / mode, defines / parameters
- SDC + directive file hashes
- tool + version, exact command
- run ID + timestamp, report path
- waiver file hash
- per-rule counts: violations / cautions / evaluations
- unresolved / inferred-clock count, "not analyzed" count

Simulation / formal additionally:
- seed, metastability-injection setting
- assertion and cover pass / fail / vacuous counts
- formal status per property with depth

Claims:
- "Structurally clean" only with all modes run and zero unwaived violations.
- "Functionally verified" additionally requires S5–S10 evidence.

---

## 10. Residual risks and human decisions

Residual risks:
- Entire analysis blocked until I1–I7 are provided.
- Reconvergence and multi-bit coherency remain open regardless of tool status until metastability-injection or formal evidence exists.

Human decisions:
1. Analysis unit and configurations / modes in scope.
2. Tool selection and metastability-injection availability.
3. Reset-ordering source of truth: spec vs reset-controller RTL.
4. Waiver approver(s) and default expiry.
5. DFT modes: in scope now or deferred.

Observed project-tooling defect:
- The uploaded 02-skill-* files use `## Required inputs` / `## Evidence gate` and have no `## Checks`, while `validate.py` requires `## Inputs`, `## Checks`, `## Evidence Gate`, and ≥1800 characters per skill. As supplied, the skills would fail validation (not executed — Derived from inspection). Decide whether to fix the skills or the validator before any CI claim.

---

## Next step

Provide I1–I3 for the first target configuration. The inventory (§2–4) will then be populated as Observed/Derived, traceability records emitted, and the S1 constraint audit run.
