# Low-Power / UPF-Aware Verification — Initialization

Date: 2026-09-24
Status: **NOT READY** — framework only (Proposed). No RTL/UPF revision, tool run, or report has been provided. Non-power-aware simulation is excluded from evidence by rule.

## 0. Scope and selected skills

- Primary skill: `low-power-upf`
- Supporting skills:
  - `cdc-rdc-reset` — power-domain crossings, reset release across domains
  - `formal-sva` — sequencing and isolation/retention protocol properties
  - `subsystem-verification` / `soc-integration-verification` — depends on DUT level
  - `coverage-closure` — once power-aware coverage databases exist
- Deferred: `signoff-audit` (applies only once evidence exists)

### Observed project-stack issue (not UPF-specific)

The stack as uploaded fails its own CI:

- `04-script-validate.py` requires headings `## Inputs`, `## Checks`, `## Evidence Gate` (case-sensitive substring match).
- `02-skill-*` files use `## Required inputs` and `## Evidence gate`, and have no `## Checks` section.
- Skill files are also under the validator's 1800-character minimum.
- Result: every skill raises errors in `validate.py`.
- Fix options: align skill headings to the validator, or relax the validator's heading list and length check. **Human decision.**

---

## 1. Intake (priority order)

| # | Item | Why it blocks |
|---|---|---|
| 1 | RTL and UPF revisions (commit IDs), UPF standard level (1801-2009/2013/2015/2018/2024), filelist, defines, parameters | Hierarchy and domain assignment can't be checked against an unknown baseline |
| 2 | Top UPF + IP-level UPFs; load/hierarchy scheme (`load_upf -scope`, `set_scope`, `apply_power_model` / `load_upf_protected`) | Flat/hierarchical mixing and scope errors are the most common consistency defects |
| 3 | Power-management spec: PMU/PPU FSM, handshake protocol (P-channel/Q-channel or custom), sequencing timing | Defines what counts as a legal transition |
| 4 | Power-state table (`add_power_state` / PST) + intended illegal states | Source for coverage and negative testing |
| 5 | Clock/reset architecture per domain; gating before or after isolation | Needed for clock/reset-during-transition and crossing checks |
| 6 | Simulator + version, PA flags, static LP tool, Liberty/`.db` with PG-pin info | Determines producible evidence |
| 7 | Existing static LP reports, PA regression results, waivers | Baseline |

Confidential RTL/UPF stays within this project.

---

## 2. Power-intent inventory (template)

Filled from UPF + RTL; each row tagged Observed or Derived.

| Domain | Elements | Primary supply set | Switchable? | Switch cell / ctrl / ack | Isolation strategy (clamp, sense, location) | Retention (elements, save/restore, balloon/zero-pin) | Level shifter (rule, location) | Always-on logic | Tag |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

---

## 3. RTL/UPF consistency checks

| ID | Check | Method | Evidence |
|---|---|---|---|
| C1 | Every `-elements` path resolves in elaborated RTL for this define/param set | Static LP + PA-sim elaboration log | Zero unresolved-scope messages |
| C2 | No instance unintentionally in default top domain | Static domain report diffed against intent table | Report path |
| C3 | Supply sets fully associated: `primary`, `default_isolation`, `default_retention`, `-function` handles | Static | Report path |
| C4 | Every switch has `-control_port` driven from AON logic and `-ack_port` consumed | Static + RTL trace | Report path |
| C5 | Every domain-boundary port has iso/LS strategy, or explicit `-no_isolation`/`-no_shift` with rationale | Static crossing report | Report path |
| C6 | Iso/ret/switch controls sourced from a domain ON in every state where needed | Static "control from off-domain" check | Report path |
| C7 | `-applies_to` and `-source/-sink` filters match intended ports; `-diff_supply_only` used deliberately | Manual + static | Review record |
| C8 | Hard IP PG pins and Liberty `pg_pin` / `related_power_pin` consistent with `connect_supply_net` | Static | Report path |
| C9 | UPF features match tool support (e.g. `add_power_state` supply-set semantics differ 2.1 vs 3.x) | Tool log | Log path |

---

## 4. Power-state and transition matrix (template)

- States: one row per `add_power_state`; one column per domain supply set (ON / OFF / RET / low-V).
- Transitions: each From→To pair classed as **Legal**, **Illegal**, or **Legal-but-sequencing-constrained**.
- Required sequence per Legal pair:
  - Power-down: clock stop → isolation assert → save → retention assert → switch off → wait for ack
  - Power-up: switch on → wait for ack → reset/restore ordering (per spec) → isolation deassert → clock start
- Illegal pairs: each row states the expected detection mechanism — PMU rejects it, an assertion fires, or the PA simulator reports it.

| From \ To | S0 | S1 | S2 | ... |
|---|---|---|---|---|
| S0 | | | | |
| S1 | | | | |

---

## 5. Isolation / retention / level-shifter matrix (template)

| Boundary signal | Src→Sink domain | Strategy | Clamp / required value | Sense | Location (self/parent/fanout) | Control source domain | LS direction / rule | Retention element | Save/restore signal | Reset-vs-restore priority |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

Clamp values are checked against functional safety of the sink, not just the UPF text:
- `req`/`valid` must clamp to the inactive level.
- An active-low signal clamped to 0 is a bug.

---

## 6. Test and assertion plan (Proposed)

Placeholder signal names; bind per switchable domain. Same properties go to formal on the PMU + control fabric. Check `disable iff` against the reset scheme.

```systemverilog
// Bound per switchable domain; placeholder signal names.
module lp_seq_checks #(int unsigned MAX_ACK_CYC = 64) (
  input logic clk_aon, rst_aon_n,
  input logic iso_en, ret_save, ret_restore, ret_en,
  input logic sw_en, sw_ack, dom_clk_en, dom_rst_n
);
  // Isolation must be active before the switch is opened; held until power good.
  a_iso_before_off: assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    $fell(sw_en) |-> iso_en);
  a_iso_held_off:   assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    !sw_ack |-> iso_en);
  // Clock stopped before isolation (policy-dependent; confirm against spec).
  a_clk_off_first:  assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    $rose(iso_en) |-> !dom_clk_en);
  // Save completes while powered; no save/restore while off.
  a_save_while_on:  assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    ret_save |-> sw_ack);
  a_no_rst_on_restore: assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    ret_restore |-> dom_rst_n);           // reset must not clobber restore (policy)
  a_restore_before_iso_rel: assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    $fell(iso_en) |-> $past(ret_restore,1,,@(posedge clk_aon)) or !ret_en); // refine per spec
  // Ack liveness (bounded) and no spurious ack.
  a_ack_bounded:    assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    $rose(sw_en) |-> ##[1:MAX_ACK_CYC] sw_ack);
  a_no_spurious_ack: assert property (@(posedge clk_aon) disable iff (!rst_aon_n)
    $rose(sw_ack) |-> sw_en);
  // Cover for non-vacuity.
  c_full_cycle: cover property (@(posedge clk_aon)
    $fell(sw_en) ##[1:$] !sw_ack ##[1:$] $rose(sw_en) ##[1:$] sw_ack ##[1:$] $fell(iso_en));
endmodule
```

`a_restore_before_iso_rel` is intentionally marked "refine per spec": restore-before-reset-release vs reset-then-restore conventions differ; not assumed.

### PA simulation test classes (constrained-random, PMU-sequencer driven)

| Test class | Content |
|---|---|
| `pa_smoke` | One full off/on cycle per switchable domain |
| `pa_pst_walk` | Randomized walk over legal PST edges, weighted toward rare edges |
| `pa_traffic_during_transition` | AXI/APB traffic in flight across the boundary at every sequencing step. Checks: no lost/duplicated beats; clamped `valid` never becomes a scoreboard transaction; retry/abort per spec |
| `pa_retention_integrity` | Save → corrupt non-retained state → restore. Retained registers compared against pre-save snapshot; non-retained expected X or reset |
| `pa_wakeup` | Interrupt/wake at each power-down phase, incl. during save and between iso-assert and switch-off |
| `pa_reg_access_off_domain` | CSR access to powered-off domain: specified error response or default data, never a hang |

Scoreboard rule: corruption-aware (ignore/expect X from off domains, keyed off the power-state monitor). No global mismatch suppression.

---

## 7. Negative and interrupted-transition scenarios

- **Abort mid power-down:** wake after iso-assert before switch-off; after switch-off before ack; during save pulse.
- **Re-request before completion:** power-up before power-down ack; back-to-back cycles with minimal dwell.
- **Illegal PST combinations:** e.g. child ON with parent OFF; low-V without LS enable. Expect PMU rejection, assertion, or PA-sim report — never silent acceptance.
- **Control faults:** ack never arrives (timeout/recovery path); ack glitch; early iso deassert (negative test, expected assertion fire).
- **Reset collisions:** AON reset during save or restore; domain reset during restore.
- **Clock faults:** clock running into isolation; clock restart before iso release.
- **Recovery:** after each illegal/aborted sequence, reach a known state and complete a clean full cycle. No stuck iso/ret; no leaked in-flight transaction.

---

## 8. Coverage plan

| Coverage item | What it covers |
|---|---|
| PST state | Every legal state entered |
| PST edge | Every legal edge taken |
| Illegal attempt | Every illegal edge attempted |
| Phase × event cross | Phases (clock-stop / iso / save / ret / off / on / restore / release) × wake, IRQ, reset, traffic |
| Per-strategy | Each iso strategy active with sink ON; each retention strategy saved→restored with data ≠ reset value; each LS in both voltage relationships if bidirectional |
| Assertion covers | Non-vacuous for every section 6 property; vacuous = not covered |

Hole classification: stimulus / observability / checker / model / unreachable / configuration / exclusion. Unreachable claims need formal or static justification.

---

## 9. Tool and evidence requirements

- **Power-aware simulation** with PA flow enabled and UPF loaded; corruption/isolation semantics actually exercised. Suggested flows (confirm against installed version):
  - VCS: NLP / `-power`
  - Xcelium: `-lps_1801`
  - Questa: `-pa`
- **Static LP:** VC LP, Conformal LP, or Questa PA static on RTL + UPF. Netlist + UPF as a separate milestone.
- **Per-run provenance:** RTL and UPF commit; tool + version; full command; defines/parameters/seed; UPF load log with zero unresolved scopes; run ID + timestamp; report paths.
- **Excluded from evidence:** non-PA runs; runs where the PA log shows UPF not applied to the relevant scope; inconclusive formal results.

---

## 10. Waiver register (per `03-schema-waiver.json`)

Fields: `id, category, target, rationale, evidence, owner, approver, expiry, status`
Categories: `coverage | cdc | rdc | lint | formal | protocol | other`

- Gap: no `lowpower` category. Either add one (schema change, needs approval) or use `other` with `LP-` id prefix. **Human decision.**
- No waivers created or altered without approval.

| id | category | target | rationale | evidence | owner | approver | expiry | status |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

---

## 11. Signoff criteria (Proposed)

| Result | Criteria |
|---|---|
| **PASS** | Static LP clean or approved waivers only; all legal PST edges and illegal attempts covered in PA sim; all section 6 assertions passing and non-vacuous; interrupted-transition set passes; zero open P0/P1 LP bugs; complete provenance |
| **CONDITIONAL** | As PASS, with bounded, owned, expiring gaps |
| **NOT READY** | Anything else |

**Current result: NOT READY** — no evidence.

---

## 12. Human decisions

1. DUT level (IP / subsystem / SoC) and UPF standard level.
2. Skill-file vs validator mismatch resolution.
3. Whether to add a `lowpower` waiver category.

## Next step

Provide intake item 1 (revisions + UPF) and the PST. Return: populated inventory (section 2) and C1–C9 findings tagged Observed/Derived.
