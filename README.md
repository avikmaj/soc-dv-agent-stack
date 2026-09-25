# SoC DV Agent Stack

A vendor-neutral, evidence-gated agent foundation for ASIC/SoC design and design verification. It provides one canonical skill library with project-local adapters for **Claude Code** and **OpenAI Codex**.

> Status: v0.1 public foundation under active validation. It supplies disciplined workflows, schemas, validation, and safety controls; it does not replace signoff tools, licensed VIP, engineering judgment, or company methodology. Review the open findings in `docs/issues/stack-issue-register.md` and `docs/audits/2026-09-24/static-security-audit.md` before production or confidential-design use.

## Scope

- IP, subsystem, SoC, NoC/interconnect, and reusable VIP workflows
- Specification analysis, verification planning, traceability, UVM, RAL/IP-XACT
- SVA/formal, CDC/RDC/reset, UPF/low power, coverage closure, regression triage
- RTL/microarchitecture review, lint/synthesis readiness, HW/SW co-verification, emulation readiness
- Claude Code and Codex adapters generated from the same canonical skills
- No automatic hooks, telemetry, network calls, global installation, or persistent learning

## Safety model

The default mode is **analyze and propose**. Agents must not claim PASS without tool evidence, invent coverage data, modify generated/vendor collateral, expose confidential design data, or run destructive/network/Git-write commands without approval. See [SECURITY.md](SECURITY.md) and [docs/threat-model.md](docs/threat-model.md).

## Quick start

```bash
git clone https://github.com/avikmaj/soc-dv-agent-stack.git
cd soc-dv-agent-stack
python scripts/validate.py
python scripts/bootstrap.py --target ../my-dv-project --harness all --dry-run
python scripts/bootstrap.py --target ../my-dv-project --harness all
```

PowerShell:

```powershell
git clone https://github.com/avikmaj/soc-dv-agent-stack.git
Set-Location soc-dv-agent-stack
python .\scripts\validate.py
python .\scripts\bootstrap.py --target ..\my-dv-project --harness all --dry-run
python .\scripts\bootstrap.py --target ..\my-dv-project --harness all
```

The bootstrapper performs project-local installation, refuses unsafe targets, does not overwrite files unless `--force` is supplied, and records a manifest for removal/review.

## Repository model

```text
skills/                 Canonical source of truth
.claude/skills/         Generated Claude Code adapter
.agents/skills/         Generated Codex adapter
schemas/                Machine-readable DV artifact contracts
templates/              Plans, matrices, and configuration examples
scripts/                Bootstrap, sync, validation, and safe tool runner
tests/                  Standard-library unit tests
docs/                   Architecture, safety, harness, and methodology docs
orgs/cupel/             Cupel verification organisation (optional layer; canonical cards, docs, schemas, adapters, tools)
.claude/agents/cupel/   Byte-identical mirror of orgs/cupel/agents/ for Claude Code
```

Never edit generated adapter copies directly. Edit `skills/<skill>/SKILL.md`, then run:

```bash
python scripts/sync_adapters.py
python scripts/validate.py
python -m unittest discover -s tests -v
```

## Core skills

| Skill | Primary deliverable |
|---|---|
| `spec-to-vplan` | Traceable verification plan and risk register |
| `microarchitecture-review` | Interface/state/invariant/PPA review |
| `rtl-design-review` | Synthesizable RTL correctness review |
| `uvm-env-architect` | Reusable UVM architecture specification |
| `uvm-agent-builder` | Protocol-agent implementation plan/review |
| `vip-qualifier` | VIP release and compliance assessment |
| `ral-ipxact` | CSR/RAL/IP-XACT consistency workflow |
| `subsystem-verification` | Multi-IP integration verification plan |
| `soc-integration-verification` | HW/SW, boot, interrupt, DMA, security plan |
| `noc-verification` | Ordering, QoS, congestion, deadlock, performance plan |
| `formal-sva` | Property plan, assumptions, proofs, vacuity closure |
| `cdc-rdc-reset` | Clock/reset domain and waiver review |
| `low-power-upf` | Power intent verification strategy |
| `coverage-closure` | Coverage gap classification and closure plan |
| `regression-triage` | Deterministic failure clustering and ownership |
| `waveform-debug` | Evidence-based root-cause workflow |
| `lint-synth-closure` | Lint, elaboration, synthesis and constraint closure |
| `hw-sw-coverification` | C/firmware-driven verification architecture |
| `emulation-readiness` | Acceleration-safe partitioning assessment |
| `signoff-audit` | Requirements-to-evidence readiness audit |

## Tool evidence contract

Every skill separates:

- **Observed:** directly present in specifications, source, logs, reports, or waveforms
- **Derived:** reasoned from observed evidence
- **Assumed:** not yet proven and explicitly tracked
- **Required evidence:** exact command/report needed to close the claim

A simulator, formal engine, lint/CDC/RDC tool, synthesis tool, coverage database, or approved review is authoritative—not model confidence.

## Configuration

Copy `templates/project-config.example.json` to `.soc-dv/config.json` in the target project. Configure commands as JSON argument arrays, not shell strings. The safe runner does not invoke a shell:

```bash
python scripts/run_tool.py --config ../my-dv-project/.soc-dv/config.json --tool lint
```

## Cupel: agentic verification organisation (optional layer)

`orgs/cupel/` adds an evidence-gated organisation of 28 agent cards (14 departments, 3 offices, 1 entry point) on top of the canonical skills, for Claude Code (`claude --agent cupel-case-marshal`), Codex and other `AGENTS.md` readers, and any chat surface through a portable prompt protocol. Its one law: a verdict is bounded above by registered evidence, never by how much has been reasoned or agreed; only the Challenge Chamber issues verdicts, and only from evidence records minted by the Evidence Vault at the pinned candidate. Read-only by default; file edits and tool execution need verbatim human sentences. See [orgs/cupel/README.md](orgs/cupel/README.md) and validate with:

```bash
python3 orgs/cupel/tools/check_parity.py
python3 orgs/cupel/tools/validate_cupel.py
python3 -m unittest discover -s orgs/cupel/tests -v
```

The stack's `scripts/validate.py` does not inspect `orgs/cupel/`; run both sets. Cupel narrows the safety model above and never relaxes it.

## License

MIT. Upstream standards, tools, specifications, and referenced repositories retain their own licenses. No third-party skill text is copied into this project.
