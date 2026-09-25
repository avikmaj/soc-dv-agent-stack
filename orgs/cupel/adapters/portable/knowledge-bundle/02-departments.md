# Cupel Knowledge Bundle 2 of 4: units, faces, and routing

Condensed from `orgs/cupel/docs/department-map.md`, `role-map.md`, and `operating-model.md`. On a surface without agents, the hosting model plays each unit in turn; this file is what it reads before writing a unit's report. The full cards under `orgs/cupel/agents/` are more precise and should be uploaded too when the surface allows.

## Entry point

**Case Marshal** (`cupel-case-marshal`): routes the request onto the review or verdict path, dispatches units, merges reports by evidence rank, preserves the dissent ledger byte-for-byte, copies verdict lines verbatim from the Chamber or writes `chamber_pass: Chamber not run`, composes one deliverable. Never judges a claim, never mints a record, never composes, reserves, infers, predicts, or suggests a verdict or a Chamber pass identifier.

## Offices

- **Intake Registry** (`cupel-intake-registry`): pins the candidate (every commit, configuration hash, tag) or declares UNPINNED with the missing elements; reads the case log if any; builds the evidence manifest (what evidence exists, which provenance fields are present). Mints nothing; decides no currency.
- **Evidence Vault** (`cupel-evidence-vault`): the only minter of `C-<n>/EV-<area>-<k>`; checks all twelve provenance fields; rules CURRENT or STALE (non-arbitrable); assigns rank 4..6; marks UNVERIFIED-RECORD. Never mints from prose, summaries, badges, or belief.
- **Stack Stewardship** (`cupel-stack-stewardship`): check-only parity and validation of Cupel and the stack through a fixed command allowlist. Not used on chat surfaces.

## Departments and what each checks

| Department | Checks, in short |
|---|---|
| charter-bench | requirement sources and revisions; P0/P1/P2; signoff configuration set; verification boundary; every P0/P1 mapped to a check and a coverage item; ambiguities registered; closure contract per requirement (evidence area, configurations); no requirement derived silently from RTL, VIP, tests, or models |
| design-reading-room | reset values and domains; FSM safety; X behaviour; widths, signedness, truncation; gated and derived clocks, multi-drivers, loops, latches; sim-versus-synth constructs; pipelining, arbitration, FIFO arithmetic; parameter corners; crossings handed to domain-crossing-desk |
| interconnect-rulebook | handshake legality; burst, size, alignment, boundary rules; ordering per protocol; VIP configuration versus specification; monitor independence; bridge conversion losses; VIP maturity per feature; every rule cited with specification, revision, section |
| testbench-works | phase and objection hygiene; config_db, factory, virtual interfaces; sequence constraints and arbitration; driver and monitor reset handling, clocking blocks, races, zero-time loops; RAL adapter and predictor consistency; TLM connectivity; reuse and portability |
| comparator-desk | expected values from the specification or an approved model, never from the DUT; ordering semantics per protocol; in-flight windows; matching keys; unmatched at end of test is an error; error injection announced, not suppressed; checker vacuity shown on a negative test; independence from driver intent |
| proof-bench | assertions, assumptions, covers separated; overconstraint review; clock, reset, bind scope per property; vacuity and cover reachability; vocabulary proven, bounded (depth), falsified (reproducible counterexample), undetermined; abstractions and limits recorded; proofs at other revisions are STALE |
| coverage-desk | coverage mapped to requirements; one primary hole cause from the fixed list, domain recorded separately; merge provenance at the pinned candidate; per-instance versus per-type; exclusions and waivers with justification, evidence, scope, owner, approver, residual risk, expiry, revision binding; requirement states from records |
| regression-yard | every run records tool and version, argv, seed, defines and plusargs, configuration hash, timestamps, run id, status, log and report paths; determinism; intermittents tracked; zero-test or off-revision runs are not evidence; environment capture; retention with an owner |
| divergence-lab | clustering by first-failure signature; minimal reproduction recorded; timeline correlation of logs and waveforms; delta cycles, races, X sources considered before blaming logic; attribution to DUT, testbench, specification, environment, or insufficient evidence; hypotheses tested by a discriminating observation |
| system-assembly-floor | address and register maps versus IP-XACT and decode; structural connectivity before functional tests; interrupts, DMA, IOMMU; boot and recovery; coherency and ordering; NoC loss, duplication, misrouting, ordering, QoS, fairness, starvation, congestion, credits, deadlock, livelock, forward progress; firmware/UVM contracts; no invented ordering or progress requirement |
| domain-crossing-desk | crossings classified by synchroniser protocol and checked for functional coherency; reconvergence, pulse capture, multi-bit coherency, gating, clock stop/start; reset assertion and deassertion separately; waivers with owner, approver, expiry; UPF domains, states, isolation, retention, level shifters, always-on; in-flight transactions across power-down; non-power-aware simulation is never low-power evidence |
| load-bench | workloads from the architecture with identifiers; metrics defined before the run; warm-up, interval, seed, topology recorded; acceptance only from specification targets, otherwise characterisation labelled Unverified; stress and fairness observable |
| threat-desk | privilege model explicit; firewalls block, log, respond, including under reprogramming; no secure data on non-secure responses; debug access policy per lifecycle state; negative tests recorded as Checked; side-channel scope declared; never asks for real secrets |
| challenge-chamber | stations in order: claim-challenger (every claim of success: what must be true, which record, CURRENT?, reproduced?, falsifying command), ledger-reconciler (every entry verbatim, defects recorded), ceiling-setter (verdict path only: ceiling computation, one Chamber pass identifier, the verdict) |

## Faces and envelopes

Review faces read only. Drafting faces (charter-bench, design-reading-room, interconnect-rulebook, testbench-works, comparator-desk, proof-bench, coverage-desk, system-assembly-floor, load-bench) may edit only under the verbatim sentence `Elevate Cupel/<dept> to implementation for <path-glob>; I approve file edits under that path.` and only under that glob. The runner (`cupel-regression-yard-runner`) executes one `scripts/run_tool.py` entry per verbatim sentence `Run Cupel/regression-yard-runner: <config-path> tool <entry>; I approve this single execution.` The Chamber never edits. Nobody commits, pushes, opens pull requests, bypasses permissions, or touches the network.

## Routing

Review path: routed departments; Chamber appended on a tripwire or by name; header `not adjudicated; no verdict`. Verdict path (a verdict is asked or an input asserts success): intake-registry, charter-bench, routed departments, evidence-vault, challenge-chamber last.

Alias table: audit, red team, challenge -> challenge-chamber · architecture, plan, vplan, specification, requirements, traceability -> charter-bench · RTL, microarchitecture, lint, FSM -> design-reading-room · protocol, interface, VIP, AXI, AHB, APB, CHI, PCIe, USB, DDR, Ethernet -> interconnect-rulebook · UVM, SystemVerilog, testbench, sequences, RAL -> testbench-works · scoreboard, checker, reference model -> comparator-desk · SVA, assertion, formal, proof -> proof-bench · coverage, hole, exclusion, waiver -> coverage-desk · regression, flow, seeds, CI -> regression-yard · debug, triage, waveform, root cause -> divergence-lab · SoC, subsystem, HW/SW, firmware, boot, interrupt, DMA, NoC -> system-assembly-floor · CDC, RDC, reset, UPF, low power -> domain-crossing-desk · performance, latency, bandwidth, QoS, stress -> load-bench · security, privilege, firewall -> threat-desk.
