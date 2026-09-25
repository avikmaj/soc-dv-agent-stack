# Claude Code Adapter

The primary Cupel carrier for Claude Code. It does not depend on `AGENTS.md` being loaded; everything Claude Code needs is under `.claude/agents/cupel/` and in the Cupel pointer block of `CLAUDE.md` (`claude-md-section.md` is the canonical text of that block).

```yaml
platform: Claude Code (CLI and IDE integrations) running in a checkout of this repository
supported_surfaces: interactive session; --print (non-interactive) session; both with --agent
instruction_mechanism: CLAUDE.md pointer block (CONFIRMED mechanism); card frontmatter and body (CONFIRMED)
repository_context: the checkout; cards use Read/Grep/Glob against it (CONFIRMED)
agent_mechanism: project subagents in .claude/agents/cupel/<face>.md with frontmatter name/description/tools (CONFIRMED mechanism; discovery in a subdirectory of .claude/agents/ REPORTED by the accepted design's runs; re-verify with a fresh run)
delegation_mechanism: the Agent tool, subagent_type = card name (CONFIRMED)
parallelism: several Agent calls issued in one assistant turn run concurrently (REPORTED in the design's T2 run; two departments returned in parallel)
tool_execution: only the runner face (scripts/run_tool.py entries) and stack-stewardship (allowlist), through their Bash tool (CONFIRMED envelope)
persistent_context: CLAUDE.md; no hooks, no MCP servers registered by Cupel (CONFIRMED: none added)
limitations:
  - a subagent cannot itself delegate; the Marshal must be the main thread (see Entry point)  # documented Claude Code behaviour; UNVERIFIED for the installed version
  - the card's tools list is enforced by Claude Code; the elevation glob is enforced by the card text and the human's review, not by the platform
  - context cost: each dispatched card is ~2-9 KB of instructions plus the dispatch block
capability_mapping:
  CAP_REPO_READ: yes (CONFIRMED)
  CAP_FILE_EDIT: drafting faces only (CONFIRMED envelope)
  CAP_COMMAND_EXECUTION: runner and stewardship only (CONFIRMED envelope)
  CAP_NATIVE_SUBAGENT: yes (CONFIRMED mechanism)
  CAP_PARALLEL_AGENT: yes (REPORTED)
  CAP_BACKGROUND_AGENT: UNVERIFIED; not used
  CAP_PERSISTENT_INSTRUCTIONS: yes (CONFIRMED)
  CAP_TOOL_RESULT_CAPTURE: yes, raw stdout in the runner's report (CONFIRMED path)
  CAP_MCP / CAP_WEB_SEARCH / CAP_GITHUB: not used by Cupel
fallback_strategy: if nested discovery fails, copy .claude/agents/cupel/*.md to .claude/agents/ (flat) and re-run check_parity.py with the mirror list adjusted; if --agent is unavailable, open a session and follow orgs/cupel/adapters/portable/prompt-protocol.md as the Marshal
invocation_examples: see below
schema_version_targeted: "1.0"
```

## Entry point

Run the Marshal as the main thread so it can delegate:

```bash
claude --agent cupel-case-marshal
claude --agent cupel-case-marshal -p "Use Cupel to review tb/axi_env/ for UVM phase and objection hygiene."
claude --agent cupel-case-marshal -p "$(cat request.md)" --output-format stream-json --verbose > case.jsonl
```

`--agent` exists in the installed CLI (`claude --help`, CONFIRMED 2026-09-25). The Marshal card lists `tools: Agent` only, so the main thread cannot read files or run commands; every observation comes from a dispatched face. Inside an ordinary session `Use the cupel-case-marshal agent to ...` reaches the Marshal as a subagent, which cannot delegate further; on that path the Marshal reports the limitation and the session itself must dispatch the departments by name (`Use the cupel-testbench-works agent to ...`), which loses the Marshal's merge and verdict-integrity controls. Prefer `--agent`.

## Face classes on this platform

| Face class | Frontmatter `tools` | Platform enforcement |
|---|---|---|
| review, office (registry, vault), Chamber | `Read, Grep, Glob` | Claude Code denies Edit, Write, Bash to the subagent |
| drafting | `Read, Grep, Glob, Edit, Write` | edits possible anywhere the session permits; the elevation glob is enforced by the card and by human review of the diff |
| runner | `Read, Grep, Glob, Bash` | Bash possible; the single command shape is enforced by the card; the session's permission prompts remain in force |
| stewardship | `Read, Grep, Glob, Bash` | as runner |
| Marshal | `Agent` | Claude Code denies every other tool |

Never run Cupel with a permission-bypass flag; the repository's control plane forbids it and the cards refuse to operate as if it were granted. Plan mode (`--permission-mode plan`) is compatible with the review path and blocks drafting and runner faces, which is a correct outcome.

## Parity and validation

```bash
python3 orgs/cupel/tools/check_parity.py            # cards mirrored byte-for-byte; counts; envelopes
python3 orgs/cupel/tools/check_parity.py --sync     # regenerate .claude/agents/cupel/ from the canonical cards
python3 orgs/cupel/tools/validate_cupel.py          # law verbatim, identifiers, tripwires, schemas, examples, links
python3 -m unittest discover -s orgs/cupel/tests -v
```

The stack's own `scripts/validate.py` and `scripts/sync_adapters.py --check` do not inspect Cupel; run both sets. CI integration for the Cupel checks is Phase 2.

## Proving that a card loaded

Loading proof is file-backed, never role-played: start a fresh `claude --agent cupel-<face> -p` process and ask it to quote its own envelope line; compare with the on-disk card. A report that describes the card from memory is not proof. The accepted design ran three such tests (T1 negated tripwire, T2 asserted success, T3 clean control); their transcripts were not preserved and the runs are REPORTED, not CONFIRMED, in this rebuild. Re-run them after installing this package (`orgs/cupel/docs/rebuild-notes.md` lists the suggested set T1..T5).

## What this adapter does not do

No hooks, no MCP servers, no settings changes, no global installation, no writes outside `orgs/cupel/`, `.claude/agents/cupel/`, and the six pointer-edited files. Bootstrapping Cupel into another project copies `orgs/cupel/` and `.claude/agents/cupel/` and adds the `CLAUDE.md` pointer block by hand; `scripts/bootstrap.py` does not know about Cupel (Phase 2).
