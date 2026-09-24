# Formal/SVA Session Framework

**Stack:** SoC DV Engineering Studio
**Primary skill:** `formal-sva`
**Created:** 2026-09-24
**Status:** Framework only. No target is loaded, so no proof status exists yet. Every result stays **Unverified** until tool evidence is provided.

---

## 0. Skill routing

The primary skill, `formal-sva`, is always in use. Each supporting skill loads only when its trigger applies:

| Supporting skill | Trigger |
|---|---|
| `rtl-design-review` | A CEX root-causes to the DUT, or a width, signedness, X or FSM concern blocks property intent. |
| `cdc-rdc-reset` | The formal boundary has more than one clock or reset domain, or an async reset is released mid-trace. |
| `noc-verification` | The target needs ordering, credit, deadlock or livelock properties on interconnect or NoC fabrics. |
| `low-power-upf` | The work is power-aware formal, covers isolation or retention properties, or has a domain-off X source in the COI. |

---

## 1. Target intake record

Complete this record for each target before any property work starts.

| Field | Content required | Evidence class |
|---|---|---|
| Target ID | `FT-<block>-<n>` | — |
| Design revision | Commit or CL, and the file-list hash | Observed only |
| Configuration | Top parameters, `define`s and generate choices. One configuration is one target. | Observed |
| Formal boundary | Top module, black-boxed or cut modules, and the cut-point list with rationale | Observed / Assumed |
| Clocks | Names, ratios, gated or derived clocks, and any `-both_edges` usage | Observed |
| Resets | Polarity, sync or async, reset-sequence length, and where the reset state comes from (sim initialization or formal reset analysis) | Observed |
| Environment | Protocol assumptions, each with its source spec clause | Assumed (owned) |
| Abstraction | Counters, memories, FIFO depth, data-width reduction, symbolic data | Assumed (owned) |
| Proof objective | Unbounded, or bounded k with justification. The justification is k ≥ reset depth + max latency + the sequential depth needed to reach every covered state. | Derived |
| Tool / version / app | JasperGold FPV, VC Formal FPV or Questa PropCheck, with the exact build | Observed |
| Existing collateral | Counts of asserts, assumes and covers; bind files; waivers with owner, approver and expiry | Observed |

---

## 2. Property ID and classification

Property IDs take the form `P-<target>-<class>-<nnn>`. Each one maps to `REQ-*` IDs through `03-schema-traceability.json`.

| Code | Class | Typical form |
|---|---|---|
| IF | Interface/protocol | Stability under stall, handshake legality, no X on valid |
| DI | Data integrity | Symbolic-data (Wolper) or tagged-token scoreboards; no corruption, loss or duplication |
| CS | Control safety | FSM legal states, one-hot encoding, no illegal transitions |
| ORD | Ordering | Per-ID or per-channel in-order delivery, AXI same-ID rules, write response only after the last beat |
| MX | Mutual exclusion | Grants are one-hot0; no concurrent owners |
| RA | Resource accounting | Credit and occupancy conservation, no overflow or underflow, outstanding ≤ N |
| SEC | Security/isolation | No path from secure to non-secure (FPV, or an SPV/taint app); firewall decode |
| RST | Reset/recovery | Reset values, outputs quiesced, no in-flight leakage across reset |
| LIV | Liveness/progress | `s_eventually` under explicit fairness assumptions; bounded response `##[1:N]` |
| COV | Cover/reachability | Antecedent witnesses and corner states such as full, empty and max outstanding |

---

## 3. Per-property audit checklist

1. **Sampling and clocking.**
   - Each property has an explicit clocking event or a `default clocking`.
   - There are no sampled-value races with interface signals.
   - Any `$past` whose depth reaches across the reset edge is guarded.
   - Multiclock sequences use `##` correctly.
2. **Reset disable.**
   - The `disable iff` polarity is correct.
   - The first cycles after reset are not hidden. An async `disable iff` masks the cycle in which reset releases.
   - RST-class properties are not themselves disabled by reset.
3. **Antecedent and consequent.**
   - `|->` versus `|=>` is chosen correctly.
   - An antecedent that can match more than once is wrapped in `first_match`.
   - A safety property does not use a weak unbounded consequent such as `##[1:$]`, which makes it vacuously weak.
   - A `cover` never contains an implication. Cover the sequence itself instead.
4. **Assumption validity.**
   - Every assume has a spec clause and an owner.
   - The same property is asserted on the upstream block, which closes the assume-guarantee loop.
   - Check for overconstraint in two ways: run the covers with and without each suspect assume, and run the tool's assumption-conflict / dead-end check.
5. **Vacuity.**
   - Every implication has a precondition cover (auto-generated or an explicit `cover` of the antecedent), and that cover must be **reached**.
   - If the precondition cover is not reached, the property is VACUOUS, not PROVEN.
6. **Cover reachability.** Classify every unreachable cover as one of:
   - overconstraint
   - a genuinely unreachable design state
   - a missing environment capability
   - insufficient depth
7. **Bounded versus unbounded.**
   - Report BOUNDED(k) with the value of k, compared against the required depth.
   - A bounded result is never promoted to PROVEN.
8. **Cone of influence and abstraction.**
   - No COI signal is cut or black-boxed unintentionally.
   - Record each abstraction as either:
     - an over-approximation: sound for proofs, but CEX may be spurious, or
     - an under-approximation: sound only for CEX and covers.
9. **Convergence.**
   - Identify the sequential depth, wide counters, memories and data paths in the COI.
   - Map each one to a remedy:
     - counter abstraction
     - symbolic data with reduced width
     - helper invariants
     - engine selection
     - a case split by configuration or mode
10. **CEX reproducibility.**
    - Record the exact TCL, configuration and seed or engine with each CEX.
    - Confirm the trace independently, by exporting it to a sim testbench or by replay.
    - Classify the root cause as DUT, property, assume gap, or spurious abstraction.
11. **Undetermined results.**
    - Report the bound reached, the engines tried and the runtime.
    - Always list the property as a residual risk, never as a pass.
12. **Waivers.**
    - Use `03-schema-waiver.json` with category `formal`.
    - Give a technical rationale, e.g. "unreachable because X, proven by P-...".
    - Owner, approver and expiry are mandatory.
    - No waiver is created or altered without explicit approval.

---

## 4. Proof-status vocabulary

These statuses are strict and must not be collapsed into each other.

| Status | Conditions |
|---|---|
| PROVEN | Unbounded result, assumptions reviewed with none in conflict, precondition covers reached, configuration and provenance recorded |
| BOUNDED(k) | No CEX up to depth k; k is stated against the required depth |
| CEX | Trace captured and reproduced; root cause pending or assigned |
| VACUOUS | The precondition is unreachable |
| UNDETERMINED | Inconclusive; the bound reached, engines and runtime are recorded |
| COVERED / UNREACHABLE | Result of a cover; an UNREACHABLE result must be classified per item 6 |
| NOT RUN / UNVERIFIED | No tool evidence exists |

---

## 5. Register templates

### 5.1 Property inventory

| ID | Class | REQ ID | File:line | Type | Clock | Disable | Depth need | Status | Evidence ref |
|---|---|---|---|---|---|---|---|---|---|
| | | | | assert/assume/cover | | | | NOT RUN | |

### 5.2 Assumption and abstraction register

| ID | Statement | Spec clause | Over/Under-approx | Affected properties | Overconstraint check | Owner | Review state |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

### 5.3 Proof-status table

| ID | Status | Engine | Depth/Bound | Runtime | Precondition cover | Run ID | Report path | Tool/Version | Commit |
|---|---|---|---|---|---|---|---|---|---|
| | NOT RUN | | | | | | | | |

### 5.4 CEX log

| ID | Trace path | First-divergence cycle | Reproduced in sim | Classification | Owner | Fix | Regression guard |
|---|---|---|---|---|---|---|---|
| | | | Y/N | DUT/property/assume/abstraction | | | |

---

## 6. House SVA conventions (proposed)

- Properties live in a checker / `bind` layer, never inside the RTL.
- Protocol property packages take an `ASSUME_INPUTS` / `ASSERT_INPUTS` parameter. The same package then acts as an assume on the DUT boundary and as an assert on the driver side, which gives assume-guarantee reuse across multi-instance IPs.
- Each checker sets a `default clocking` and a `default disable iff`. RST properties override these explicitly.
- Liveness properties go in separate LIV checkers with named fairness assumes. Each has a bounded-response safety twin, which helps convergence and can be reused in simulation.
- Every assert has a companion antecedent cover. Every assume has a sanity cover showing the environment can still exercise it.

---

## 7. Command skeletons

These skeletons are **Unverified** against your installed builds. Confirm the switches for your tool version before use.

### JasperGold FPV

```tcl
analyze -sv12 -f rtl.f -f sva.f +define+<CFG>
elaborate -top <top> -parameter {<P> <v>} -create_related_covers {witness precondition}
clock <clk>
reset -expression {!<rst_n>}
prove -all
report -file reports/<target>_<runid>.txt
```

### VC Formal FPV

```tcl
set_fml_appmode FPV
read_file -top <top> -format sverilog -sva -vcs {-f rtl.f -f sva.f +define+<CFG>}
create_clock <clk> -period 100
create_reset <rst_n> -sense low
sim_run -stable; sim_save_reset
check_fv -block
report_fv -list > reports/<target>_<runid>.txt
```

### Questa PropCheck

```sh
qverify -c -od out -do "formal compile -d <top> -G<P>=<v>; formal verify -init init.tcl -timeout 2h; exit"
```

### Expected evidence per run

Every run must produce:

- the tool version string
- the commit
- the file-list and configuration hash
- the full TCL
- the engine and effort settings
- the status of each property, with its bound
- the precondition-cover results
- the assumption-conflict report
- the CEX and witness databases
- the run ID and timestamp

---

## 8. Stack findings

These findings are **Observed** in the uploaded files.

- `04-script-validate.py.txt` requires these headings: `## Inputs`, `## Checks`, `## Evidence Gate`. It also requires at least 1800 characters per skill.
- The uploaded `02-skill-*.md` files differ on all four points:
  - they use `## Required inputs` instead of `## Inputs`
  - they use `## Evidence gate` (lowercase "g") instead of `## Evidence Gate`
  - they have no `## Checks` section
  - they are about 1.3 KB long
- If these files are the canonical `skills/` sources, `validate.py` and CI will fail on all 20 of them.
- `04-contributing.md` sides with the validator, so the likely fix is to align the skills to it.

**Human decision:** align the skill headings to the validator, or relax the validator.

---

## 9. Inputs needed to start the first target

1. The top module and file list, or the relevant RTL excerpts
2. The configuration parameters and defines
3. A description of the clocks and resets
4. The interface spec clauses behind the assumptions
5. The tool and version
6. Any existing SVA and TCL, plus the last run report or CEX

The fastest path is an existing formal report together with its TCL. That lets the work start with the proof-status and vacuity audit.
