# UVM Environment Architecture — Intake and Initialization

Status: **Intake pending**. No architecture proposed yet. All content below is Proposed or Derived; nothing is Observed until compiled and run on the target simulator.

---

## 1. Scope and skill routing

| Item | Value |
|---|---|
| Primary skill | uvm-env-architect |
| Supporting skills | uvm-agent-builder (per-protocol agent contracts); ral-ipxact (map source of truth, adapter, predictor, mirror); spec-to-vplan (entry point if requirement IDs don't exist); coverage-closure (covergroup-to-requirement model); regression-triage (log/signature/seed contract) |
| Held back | emulation-readiness (only if emulation in scope); hw-sw-coverification (only if C/firmware interaction); signoff-audit (only once evidence exists) |
| Phase deliverable | Intake-validated architecture spec covering all 12 requested artifacts. No code until approved. |

---

## 2. Intake template

Fill and return. Use `N/A` where not applicable.

```yaml
dut:
  name:
  level:                 # IP | subsystem | SoC
  boundary:              # what is inside the DUT vs modeled/stubbed
  spec_refs:             # doc IDs + revisions; known conflicts
  requirement_ids:       # exist? (if no -> start with spec-to-vplan)
interfaces:              # one entry per interface type
  - name:
    protocol:            # e.g. AXI4 / ACE-Lite / CHI-E / APB4 / AXI-S / custom
    profile:             # data/addr/id/user widths, outstanding depth, ordering model, optional signals
    role_of_tb:          # active-initiator | active-responder | passive
    instances:           # count, and whether it is parameterized per instance
    existing_vip:        # in-house / commercial (which) / none
    clock_domain:
    reset_domain:
clocks_resets:
  clocks:                # name, freq range, ratios, gating, dynamic freq change?
  resets:                # name, sync/async assert/deassert, domain, sequencing rules
  mid_sim_reset:         # required? which domains independently?
  power_domains:         # UPF present? retention/isolation affecting TB?
config_profiles:         # named DUT parameter sets / defines / build variants to verify
ral:
  source_of_truth:       # IP-XACT | SystemRDL | spreadsheet | hand-written
  generator:             # ralgen / PeakRDL / in-house / none
  bus_for_access:        # APB / AXI-Lite / sideband
  maps:                  # count, multi-map? aliasing? paged/banked?
  special_fields:        # W1C/RC/volatile/HW-updated/side-effect/FIFO registers
  backdoor:              # hdl_path available? stable across synthesis/gate/emulation?
reference_model:
  exists:                # yes/no; language (SV / C / C++ via DPI / SystemC)
  granularity:           # transaction-accurate | cycle-approximate | cycle-accurate
  ownership_and_trust:   # who maintains it, is it golden?
checking:
  end_to_end:            # which paths need data integrity + ordering checks
  ordering_rules:        # per-ID, per-address, per-stream, none
  performance_checks:    # latency/throughput/QoS targets? measured how?
  error_semantics:       # SLVERR/DECERR/poison/parity/ECC handling expected
sw_interaction:
  c_tests:               # yes/no; CPU model or real core RTL? boot flow?
  sync_mechanism:        # mailbox / shared memory / backdoor / DPI
tools:
  simulators:            # VCS / Xcelium / Questa + versions; must all be supported?
  uvm_version:           # 1.1d / 1.2 / IEEE 1800.2-2017 / 2020
  constraints:           # e.g. no DPI, no hierarchical refs, no class-based vif tricks
reuse:
  vertical:              # IP env must embed passively in subsystem/SoC env?
  horizontal:            # other projects/derivatives consume this env?
  emulation:             # none / planned (platform) / accelerated-sim; timeline
  existing_infra:        # regression system, coverage DB, triage tooling to integrate with
constraints:
  confidentiality:       # can spec/RTL excerpts be shared, or abstract only?
  schedule:              # milestones driving implementation order
```

---

## 3. Highest-impact decisions

Answer these first if time is short.

1. **Level and vertical reuse.** An IP env that must embed passively in a subsystem env forces the following from day one:
   - hierarchical config objects;
   - no global `config_db` wildcards;
   - scoreboard enable controls;
   - per-instance `is_active`;
   - no direct vif access from sequences.
2. **Reference model trust and granularity.** This determines the scoreboard shape:
   - A transaction-accurate golden model gives a predictor-in-front, compare-at-output scoreboard.
   - No model gives a protocol-rule checker plus data-integrity tracker, with ordering checked per ordering domain.
   - A cycle-accurate model is usually the wrong target for a UVM scoreboard.
3. **Mid-sim reset per domain.** If required, every driver, monitor, predictor and scoreboard needs a reset-abort contract. It also needs:
   - a reset-aware main loop instead of phase jumping;
   - a per-component in-flight flush/retire policy.
4. **RAL source of truth and access bus.** This drives:
   - the adapter (bus2reg/reg2bus, response-status mapping, byte enables);
   - the prediction mode, with explicit prediction as the default for any bus with outstanding or out-of-order traffic;
   - backdoor viability on emulation.
5. **Emulation.** If planned, the HVL/HDL split must be decided up front:
   - BFM tasks live in synthesizable interfaces, and the class side calls them;
   - no `#delay` in classes;
   - restricted backdoor use.

   Retrofitting later means rewriting drivers and monitors.
6. **UVM version and simulator set.** Mixed 1.1d / 1800.2 support constrains:
   - `uvm_reg` access policies;
   - the objection drain API;
   - factory access patterns;
   - report-catcher semantics.

---

## 4. Proposed defaults (applied if items are left blank)

Each default is labeled **Assumed** and owned in the architecture spec.

| Area | Default |
|---|---|
| Library / portability | UVM 1.2 source-compatible with IEEE 1800.2-2020; portable across VCS, Xcelium and Questa; no vendor-only constructs in library code |
| Configuration | One config object per agent instance. Env config holds an array of agent configs. `config_db` is used only at the test→env boundary, with explicit paths and no wildcards. |
| Monitors | Always present and independent of the driver. The sole source of truth for checkers and coverage. |
| RAL | Explicit prediction via `uvm_reg_predictor` on the monitored bus; `auto_predict` off |
| End of test | Objections only in the top virtual sequence. Scoreboard drain via `phase_ready_to_end` with a bounded drain time, plus a global watchdog timeout. Any mismatch or unretired entry is fatal at `check_phase`, with a summary in `report_phase`. |
| Reproducibility | Seed, config profile and plusargs logged at time 0 in a machine-parseable header aligned to `03-schema-regression-result.json` |

---

## 5. Observed issues in project collateral

| Area | Observed | Impact / proposed fix |
|---|---|---|
| Skill headings vs validator | `04-script-validate.py` requires `## Inputs`, `## Checks`, `## Evidence Gate`. The `02-skill-*` files use `## Required inputs` and `## Evidence gate`, and have no `## Checks`. | **Derived:** the validator would report errors on all 20 skills if these are the canonical sources. The CI/validation claim in `04-changelog.md` is **Unverified** without a run log. Fix: align headings or the validator. |
| Skill length gate | `validate.py` enforces `len(s) >= 1800`; the uploaded skills are about 1.3–1.5 KB each. | **Derived:** the "insufficient detail" check fails on all 20. |
| Regression schema | `03-schema-regression-result.json` lacks `uvm_version`, `plusargs`, `defines`, `config_profile` and `timeout`/`kill_reason`. | Needed for the reproducibility contract. A schema delta is to be proposed, pending approval. |
| Traceability schema | `03-schema-traceability.json` has no covergroup/bin granularity and no `config_profile`. | Per-profile requirement closure is not expressible. |

---

## 6. Deliverables after intake is returned

1. Architecture diagram (Mermaid)
2. Component-responsibility table
3. Transaction-flow table
4. Configuration hierarchy
5. Phase and reset strategy
6. Scoreboard/reference-model architecture
7. RAL integration plan
8. Sequence/test taxonomy
9. File/package structure
10. Implementation order
11. Validation plan
12. Assumptions and human-decision log

**Preconditions:**
- If requirement IDs don't exist, spec-to-vplan runs first and produces a minimal requirement set; otherwise the traceability table has nothing to trace to.
- If the DUT is confidential, an abstracted interface/role/instance description is sufficient. RTL and spec text are not needed at this stage.
