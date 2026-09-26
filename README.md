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

The bootstrapper writes only to paths under the target directory, but it follows any symbolic links already present there, so a link can redirect a write outside the target (audit F2). Its target check is narrow: it refuses exactly two targets, the home directory and the filesystem root (exit 2), and accepts every other path, including system directories and directories that are not Git repositories (audit F8). It refuses to overwrite an existing file whose content differs from the source (exit 3, also under `--dry-run`) unless `--force` is supplied; `--force` overwrites those files in place, takes no backup, and the manifest records only the post-install hashes (audit F9). The manifest, `.soc-dv/install-manifest.json`, is written last and is for review only: no uninstall or rollback command exists and nothing reads it back. Skill files are copied from the generated adapter trees (`.claude/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md`), not from `skills/` (audit F18). The full contract is in [docs/scripts.md](docs/scripts.md).

## Repository model

```text
skills/                 Canonical source of truth
.claude/skills/         Generated Claude Code adapter
.agents/skills/         Generated Codex adapter
schemas/                Machine-readable DV artifact contracts
templates/              Plans, matrices, and configuration examples
scripts/                Bootstrap, sync, validation, and shell-free tool runner (see docs/scripts.md)
tests/                  Standard-library unit tests
docs/                   Architecture, safety, harness, and methodology docs
orgs/cupel/             Cupel verification organisation (optional layer; canonical cards, docs, schemas, adapters, tools)
.claude/agents/cupel/   Byte-identical mirror of orgs/cupel/agents/ for Claude Code
```

Never edit generated adapter copies directly. Edit `skills/<skill>/SKILL.md`, then run:

```bash
python scripts/sync_adapters.py --check   # exit 1 lists the adapter trees the next command replaces
python scripts/sync_adapters.py
python scripts/validate.py
python -m unittest discover -s tests -v
```

`sync_adapters.py` without flags rewrites `.claude/skills/` and `.agents/skills/` into byte-identical copies of `skills/`: each drifted tree is rebuilt in a sibling staging directory and swapped in with atomic renames, and anything in those two directories that is not in `skills/` is removed. `--check` is the non-destructive mode (exit 1 on drift, exit 0 on parity, nothing modified); `--dry-run` runs the same guards and prints the plan. Other entries under `.claude/` and `.agents/`, such as `.claude/agents/`, are left alone. Exit codes 0-6 are listed in [docs/scripts.md](docs/scripts.md).

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

Copy `templates/project-config.example.json` to `.soc-dv/config.json` in the target project (the bootstrapper does this when no `config.json` exists). Configure commands as JSON argument arrays, not shell strings. The runner does not invoke a shell:

```bash
python scripts/run_tool.py --config ../my-dv-project/.soc-dv/config.json --tool lint --dry-run
python scripts/run_tool.py --config ../my-dv-project/.soc-dv/config.json --tool lint
```

`run_tool.py` reads `tools.<name>.argv`, `tools.<name>.cwd` (default `.`), `tools.<name>.timeout_seconds` (default 3600) and the top-level `environment_allowlist`; the other keys in the example file (`schema_version`, `project_root`, `allowed_workdirs`) are not consulted. The project root is the parent of `.soc-dv/` when the config file lives there, otherwise the config file's directory. The runner prints the plan (`argv`, `cwd`, `timeout_seconds`) to stdout, stops there under `--dry-run`, and otherwise runs `argv` with `shell=False` and exits with the child's return code.

The environment allowlist is default-deny: the child receives only the variables named in `environment_allowlist` and nothing else, `PATH` included. When `PATH` is not allowlisted, the executable is looked up on Python's `os.defpath` (`/bin:/usr/bin` on POSIX), so tool resolution depends on the host (issue register ISS-013; audit H4, F17). The allowlist is not filtered, so a variable named in it is passed whatever it contains (audit F3).

Exit codes: `0` success or `--dry-run`; `2` unknown tool name (also command-line usage errors); `3` `argv` is not a non-empty array of non-empty strings; `4` the resolved `cwd` is outside the project root; otherwise the child's exit status (a child killed by signal `N` maps to `256 - N`, audit H6). A timeout kills only the direct child and surfaces as an uncaught `subprocess.TimeoutExpired` traceback (exit 1), as does a missing or malformed config file (audit F10, F15). The runner enforces no approval record and writes no run record (audit F3, F10); see [docs/scripts.md](docs/scripts.md).

## Cupel: agentic verification organisation (optional layer)

`orgs/cupel/` adds an evidence-gated organisation of 28 agent cards (14 departments, 3 offices, 1 entry point) on top of the canonical skills, for Claude Code (`claude --agent cupel-case-marshal`), Codex and other `AGENTS.md` readers, and any chat surface through a portable prompt protocol. Its one law: a verdict is bounded above by registered evidence, never by how much has been reasoned or agreed; only the Challenge Chamber issues verdicts, and only from evidence records minted by the Evidence Vault at the pinned candidate. Read-only by default; file edits and tool execution need verbatim human sentences. See [orgs/cupel/README.md](orgs/cupel/README.md) and validate with:

```bash
python3 orgs/cupel/tools/check_parity.py
python3 orgs/cupel/tools/validate_cupel.py
python3 -m unittest discover -s orgs/cupel/tests -v
```

The stack's `scripts/validate.py` does not inspect `orgs/cupel/`; run both sets. Cupel narrows the safety model above and never relaxes it.

## Scope and limitations

This repository is a pre-release foundation under active validation; it makes no production-readiness or security-review claim. The scripts are small standard-library tools with documented limits, listed per script in [docs/scripts.md](docs/scripts.md): the installer follows symbolic links, takes no backup under `--force`, and refuses only two targets (audit F2, F9, F8); the runner enforces no approval, records no evidence, and reports timeouts and malformed configuration as tracebacks (audit F3, F10, F15); `validate.py` enforces no minimum skill or schema count and validates no artifact against a schema (audit F4, F6); Windows portability is partial (audit F17). `VERSION` is the single source of the stack version; `pyproject.toml` and the head of `CHANGELOG.md` must agree with it, and no automated check enforces that agreement (audit F19). Open findings are recorded in [docs/audits/2026-09-24/static-security-audit.md](docs/audits/2026-09-24/static-security-audit.md) and [docs/issues/stack-issue-register.md](docs/issues/stack-issue-register.md); those two documents, not this README, hold each finding's status.

## License

MIT. Upstream standards, tools, specifications, and referenced repositories retain their own licenses. No third-party skill text is copied into this project.
