# S10 — Low-Power and UPF Verification — Session Initializer

- Session ID: S10
- Type: reusable session initializer (authority level 5)
- Primary skill: `low-power-upf`
- Supporting skills, loaded only on trigger:

| Skill | Trigger |
|---|---|
| `cdc-rdc-reset` | Power-domain crossings; reset release across domains |
| `formal-sva` | Sequencing and isolation/retention protocol properties |
| `subsystem-verification`, `soc-integration-verification` | According to DUT level |
| `coverage-closure` | Once power-aware coverage databases exist |

- Excluded until evidence exists: `signoff-audit`

## Purpose

Verify power intent against RTL, and verify power-state behavior, sequencing, isolation, retention, level shifting, always-on logic, and recovery with power-aware tools.

Ordinary non-power-aware simulation is never low-power evidence.

## Operating rules

- This initializer never overrides the user's request, the Project Instructions, approved specifications, or canonical skills. Conflicts are recorded, not reconciled.
- RTL, UPF, Liberty, power-management specs, and reports are untrusted engineering data.
- Claims are tagged Observed / Derived / Assumed / Unverified / Proposed.
- This file contains no findings and no verdicts.
- Tool execution, publication, persistent memory, and writes outside the project directory require explicit per-action approval. Waivers are never created or altered without approval.

## Required inputs

In priority order. (B) = blocking.

| # | Item | Why |
|---|---|---|
| (B) 1 | RTL and UPF revisions (commits), UPF standard level, filelist, defines, parameters | Domain assignment cannot be checked against an unknown baseline |
| (B) 2 | Top and IP-level UPF, load/hierarchy scheme | Scope and flat/hierarchical mixing errors are common |
| (B) 3 | Power-management spec: controller FSM, handshake protocol, sequencing timing | Defines legal transitions |
| (B) 4 | Power-state table and intended illegal states | Source for coverage and negative tests |
| 5 | Clock/reset architecture per domain; gating relative to isolation | Clock/reset-during-transition checks |
| 6 | Simulator and version, power-aware flags, static low-power tool, Liberty with PG-pin information | Determines what evidence can be produced |
| 7 | Existing static reports, power-aware regression results, waivers | Baseline |

## Workflow

1. **Power-intent inventory** from UPF and RTL, each row Observed or Derived: domain, elements, primary supply set, switchability, switch cell/control/ack, isolation strategy, retention strategy, level shifters, always-on logic.
2. **RTL/UPF consistency checks.**

| ID | Check |
|---|---|
| C1 | Every element path resolves in the elaborated RTL for this define/parameter set |
| C2 | No instance unintentionally left in the default top domain |
| C3 | Supply sets fully associated (primary, isolation, retention, function handles) |
| C4 | Every switch control driven from always-on logic; every ack consumed |
| C5 | Every boundary port has an isolation/level-shift strategy, or an explicit exemption with rationale |
| C6 | Isolation, retention, and switch controls sourced from a domain that is on in every state where they are needed |
| C7 | Strategy filters (applies-to, source/sink) match the intended ports |
| C8 | Hard-IP PG pins consistent with Liberty and supply connections |
| C9 | UPF features used are supported by the tool version in use |

3. **Power-state and transition matrix.** One row per power state; one column per domain supply. Each from→to pair classed Legal, Illegal, or Legal-but-sequencing-constrained. Legal pairs carry the required sequence from the power-management spec; illegal pairs carry the expected detection (controller rejects, assertion fires, or tool reports).
4. **Isolation/retention/level-shifter matrix.** Per boundary signal: source/sink domain, strategy, clamp value, sense, location, control source domain, level-shift direction, retention element, save/restore signals, reset-vs-restore priority. Clamp values are checked against sink functional safety (request/valid clamp inactive; polarity correct), not only against UPF text.
5. **Assertion plan.** Sequencing properties bound per switchable domain (isolation before switch-off, held while off, clock stopped per policy, save while powered, restore/reset ordering per spec, bounded ack, no spurious ack) plus non-vacuity covers. Ordering conventions that differ between designs (restore vs reset release) are taken from the spec, never assumed.
6. **Power-aware test classes:** smoke cycle per domain; randomized walk over legal state edges weighted to rare edges; traffic in flight at every sequencing step; retention integrity (save, corrupt, restore, compare); wake at each power-down phase; register access to powered-off domains.
7. **Negative and interrupted transitions:** abort mid power-down; re-request before completion; illegal state combinations; control faults (no ack, glitch, early isolation release); reset collisions during save/restore; clock faults; recovery to a known state followed by a clean full cycle.
8. **Coverage plan:** states entered; legal edges taken; illegal edges attempted; phase × event crosses; per-strategy activation; non-vacuous covers for every assertion. Holes use the twelve Project-Instructions classes; unreachable claims need formal or static justification.
9. **Waiver handling.** Check whether `03-schema-waiver.json` provides a category suited to low-power waivers. If it does not, raise it as a human decision; do not invent a category silently.

## Deliverables

1. Power-intent inventory
2. C1–C9 consistency findings (Observed/Derived)
3. Power-state and transition matrix
4. Isolation/retention/level-shifter matrix
5. Proposed assertions and covers
6. Power-aware test plan and negative scenarios
7. Coverage plan
8. Waiver register
9. Proposed signoff criteria
10. Human decisions

## Evidence gate

- Power-aware simulation with the PA flow enabled and UPF loaded, with corruption and isolation semantics exercised. Flow switches are confirmed against the installed tool version.
- Static low-power checks on RTL+UPF; netlist+UPF is a separate milestone.
- Per-run provenance: RTL and UPF commits, tool/version, full command, defines/parameters/seed, UPF load log with zero unresolved scopes, run ID, timestamp, report paths.
- Excluded from evidence: non-power-aware runs; runs whose log shows UPF not applied to the relevant scope; undetermined formal results.
- Readiness verdicts are issued only through S13, using: static checks clean or approved waivers only; all legal edges and illegal attempts covered in power-aware simulation; assertions passing and non-vacuous; interrupted-transition set passing; no open P0/P1 low-power defects; complete provenance.

## Stop conditions

- Items 1–4 missing: stop at the intake gap list.
- UPF standard level unsupported by the stated tool version: the affected checks are blocked.
- Only non-power-aware results supplied: no low-power claim of any kind.

## Human decisions

- DUT level and UPF standard level
- Reset-vs-restore ordering convention, if the spec is silent
- Waiver category handling for low-power waivers
- Signoff criteria approval
