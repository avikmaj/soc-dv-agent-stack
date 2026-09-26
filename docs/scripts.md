# Scripts reference

The four scripts under `scripts/` are standard-library Python (3.10 or later per `pyproject.toml`; CI runs 3.12) and are invoked as `python scripts/<name>.py`. This page documents what each one reads, writes, and deletes, its exit codes, and its known limitations, as implemented in this checkout. Where the page and the code disagree, the code is authoritative and the page needs correcting. Limitations carry the finding ID from [audits/2026-09-24/static-security-audit.md](audits/2026-09-24/static-security-audit.md) (`F`/`H` IDs) or [issues/stack-issue-register.md](issues/stack-issue-register.md) (`ISS` IDs); those two documents, not this page, record each finding's status.

Common to all four: `-h`/`--help` prints the argument list; a command-line usage error exits `2` (argparse); an uncaught Python exception exits `1` with a traceback. `bootstrap.py`, `sync_adapters.py`, and `validate.py` locate the repository root relative to their own file, so they run from a checkout (`sync_adapters.py` also imports its sibling `fssafety.py`); `run_tool.py` derives the project root from the config path instead. None of them accesses the network, installs packages, or runs Git.

## bootstrap.py: project-local installer

**Purpose.** Copy the agent contract files and the generated skill adapters into another project so that Claude Code and Codex find them there.

**Usage.**

```bash
python scripts/bootstrap.py --target <dir> [--harness claude|codex|all] [--dry-run] [--force]
```

`--harness` defaults to `all`. `--dry-run` prints the plan (`<source> -> <destination>`, one line per file) and writes nothing, not even the target directory.

**Reads.** `CLAUDE.md` (harness `claude` or `all`), `AGENTS.md` (`codex` or `all`), every `.claude/skills/*/SKILL.md` and `.agents/skills/*/SKILL.md` from the generated adapter trees of this checkout (not from `skills/`, and only the `SKILL.md` of each skill), `templates/project-config.example.json`, and `VERSION` (read after the copies, for the manifest). Existing destination files are hashed to detect conflicts.

**Writes.** All under `<target>`:

| Destination | Source | Condition |
|---|---|---|
| `CLAUDE.md` | `CLAUDE.md` | harness `claude` or `all` |
| `.claude/skills/<skill>/SKILL.md` (one per skill; 20 at this checkout) | `.claude/skills/<skill>/SKILL.md` | harness `claude` or `all` |
| `AGENTS.md` | `AGENTS.md` | harness `codex` or `all` |
| `.agents/skills/<skill>/SKILL.md` (one per skill) | `.agents/skills/<skill>/SKILL.md` | harness `codex` or `all` |
| `.soc-dv/config.json` | `templates/project-config.example.json` | only when the destination does not exist; an existing `config.json` is never compared or overwritten, even with `--force` |
| `.soc-dv/install-manifest.json` | generated | every non-dry run; written last and overwritten unconditionally |

Missing parent directories are created. Files are copied with `shutil.copy2`, one at a time, in the printed order. The manifest is a JSON object with `stack_version` (the content of `VERSION`), `harness`, and `files`, a list of `{path, sha256}` entries for the files copied in that run only (an existing `config.json` that was skipped is not listed). Nothing reads the manifest back.

**Deletes.** Nothing. There is no uninstall, rollback, or backup; removing an installation means deleting the listed files by hand.

**Conflict rule.** Before anything is copied, every destination that exists and whose SHA-256 differs from its source is listed; if any exist and `--force` is absent, the run stops with exit `3` and nothing is written. The check runs under `--dry-run` too, so a dry run against a target with local edits also exits `3`. With `--force` the differing files are overwritten in place.

**Exit codes.**

| Code | Meaning |
|---|---|
| `0` | Plan printed (`--dry-run`), or installation completed and manifest written |
| `2` | Target is the home directory or the filesystem root (`Refusing home/root target`), or a usage error |
| `3` | One or more existing destination files differ and `--force` was not given; nothing written |
| `1` | Uncaught exception, for example `VERSION` missing from the checkout: the files already copied stay in place and no manifest is written (audit F14) |

**Known limitations.**

- Writes follow symbolic links present in the target. A dangling link at a destination path is not detected as a conflict (`Path.exists()` is false for it), so the file is created at the link's destination, possibly outside the target; with `--force`, an existing symlinked file is written through the link (audit F2).
- The target check refuses exactly two paths, the home directory and the resolved filesystem root. System directories, the stack checkout itself, and directories that are not Git repositories are accepted; the audit also notes that on Windows only the current drive's root is covered (audit F8).
- `--force` keeps no backup of the files it overwrites, and the manifest records only the post-install hashes, so the previous content cannot be recovered from it (audit F9).
- Copies are not atomic and the sources are not checked before writing starts: a failure part-way leaves a partial installation without a manifest (audit F14).
- The skills are taken from the generated adapter trees without checking their parity with `skills/`, and only `SKILL.md` is copied, so any other file in a skill directory would be left out (audit F18). Run `python scripts/sync_adapters.py --check` in the checkout first.
- Checks and writes are separate system calls, so a concurrent same-user process could swap a path between them (audit H1).

## sync_adapters.py: adapter synchronization

**Purpose.** Materialize the canonical `skills/` tree into the two generated adapter trees, `.claude/skills/` and `.agents/skills/`, without following links, and report drift between them.

**Usage.**

```bash
python scripts/sync_adapters.py            # rewrite drifted adapter trees from skills/
python scripts/sync_adapters.py --check    # report drift only; exit 1 on drift; modify nothing
python scripts/sync_adapters.py --dry-run  # run every guard and print the plan; modify nothing
```

`--check` and `--dry-run` are mutually exclusive (giving both is a usage error, exit `2`).

**Reads.** The whole `skills/` tree, every regular file in it (not only `SKILL.md`), plus the two target trees for comparison. Parity is strict: identical entry sets and kinds, byte-identical regular files, and no links on either side.

**Writes and deletes.** Only in the two target directories and their parents `.claude/` and `.agents/`. All guards run for both targets before anything is modified. A target already in parity is left untouched (`in sync, unchanged`). A drifted or missing target is rebuilt: the source is copied to a sibling staging directory `.claude/.skills.staged-<pid>-<hex>` (or `.agents/...`), verified against the source, the existing tree is renamed to `.skills.old-<pid>-<hex>`, the staged tree is renamed into place, and the old tree is then deleted through the same link-refusing guard. **The result is a byte-identical copy of `skills/`: every file in `.claude/skills/` or `.agents/skills/` that is not in `skills/` is removed.** A missing `.claude/` or `.agents/` parent is created with a plain `mkdir`. Other entries in those parents, such as `.claude/agents/`, are not touched. `--check` and `--dry-run` write nothing.

**Exit codes** (from the module docstring; stable).

| Code | Meaning |
|---|---|
| `0` | Synchronized, or parity confirmed (`Adapter parity: OK`) |
| `1` | `--check` found drift (`Adapter drift: <targets>` on stderr) |
| `2` | Command-line usage error |
| `3` | Unsafe path state: a symbolic link, junction, or reparse point in the root-to-target chain or inside `skills/`, a target that is not a directory, or a resolved path outside the repository; nothing modified (`ERROR[unsafe-path]`) |
| `4` | `skills/` missing or containing no files (fail closed); nothing modified (`ERROR[source-tree]`) |
| `5` | I/O failure while staging or swapping; the previous target was left in place or restored (`ERROR[swap-failed]`) |
| `6` | Leftover `.skills.staged-*` or `.skills.old-*` directories from an interrupted earlier run; inspect and remove them by hand; nothing modified (`ERROR[leftover-state]`) |

**Known limitations.**

- The guards and the operations they protect are separate system calls; a same-user process racing between them can still win a narrow window. On POSIX the deletion step walks the directory chain with `O_NOFOLLOW` descriptors and, on Python 3.11 or later, deletes relative to that descriptor; the rename steps and all Windows code paths rely on `lstat` checks made immediately before each operation (`scripts/fssafety.py` docstring; audit F1 residual risk, H1).
- It covers only `.claude/skills/` and `.agents/skills/`. The Cupel mirror under `.claude/agents/cupel/` is checked by `orgs/cupel/tools/check_parity.py`.
- Windows junction handling is exercised only by two Windows-only tests, which run in the `f1-windows-junction-validation` CI job and are skipped on POSIX hosts.

## run_tool.py: shell-free tool runner

**Purpose.** Run one tool entry from a project's `.soc-dv/config.json` as an argument array with `shell=False`, from a working directory inside the project, with a filtered environment.

**Usage.**

```bash
python scripts/run_tool.py --config <project>/.soc-dv/config.json --tool <name> [--dry-run]
```

**Reads.** The config file (JSON). Only these keys are used: `tools.<name>.argv` (required: a non-empty array of non-empty strings), `tools.<name>.cwd` (default `.`, relative to the project root), `tools.<name>.timeout_seconds` (default `3600`), and the top-level `environment_allowlist` (default empty). `schema_version`, `project_root`, and `allowed_workdirs` from the example file are not consulted. The project root is the parent of `.soc-dv/` when the config file is inside a `.soc-dv/` directory, otherwise the config file's own directory; `cwd` is resolved (links followed) and must remain inside that root.

**Environment.** Default-deny. The child receives exactly the parent's variables whose names appear in `environment_allowlist`, and no others, `PATH` included. If `PATH` is not allowlisted, the executable is found via Python's `os.defpath` (`/bin:/usr/bin` on POSIX), so which binary runs depends on the host (issue register ISS-013; audit H4). On Windows the child also lacks `SYSTEMROOT` and `PATHEXT` unless they are allowlisted (audit F17). The allowlist itself is not filtered: a variable named in it is passed whatever it contains (audit F3).

**Writes.** Nothing. The plan (`argv`, `cwd`, `timeout_seconds`) is printed to stdout as JSON before execution, so the `argv` values appear in any captured log; the child inherits stdout and stderr, and no run record, log, or result file is produced (audit F10; issue register ISS-014). `--dry-run` stops after printing the plan.

**Exit codes.**

| Code | Meaning |
|---|---|
| `0` | `--dry-run` completed, or the child exited 0 |
| `2` | `--tool` names no entry under `tools` (`Unknown tool: <name>`), or a usage error |
| `3` | `argv` is missing, not an array, empty, or contains a non-string or empty string |
| `4` | The resolved `cwd` is outside the project root |
| child's status | The child's return code is propagated unchanged; a child killed by signal `N` yields `256 - N` (audit H6) |
| `1` | Uncaught exception with traceback: config file missing or not valid JSON, `tools.<name>` not an object, `timeout_seconds` that `int()` cannot convert, or the timeout expiring (`subprocess.TimeoutExpired`) (audit F10, F15) |

**Known limitations.**

- No approval is checked or recorded. Whatever `argv` the config names is executed with the caller's full privileges; `shell=False` only prevents shell parsing of the arguments, it does not restrict what the named program does, and `cwd` containment does not bound what the process touches (audit F3). Approval requirements live in `AGENTS.md` and `CLAUDE.md` and are enforced by the operator, not by this script.
- On timeout, `subprocess.run` kills only the direct child; processes it spawned keep running, and the expiry surfaces as a traceback rather than a structured exit code (audit F10).
- A zero or negative `timeout_seconds` is accepted and expires immediately; malformed configuration produces tracebacks instead of distinct exit codes (audit F15).
- No evidence record is produced, so runner output cannot by itself support a PASS claim under the evidence contract (issue register ISS-014).

## validate.py: repository validator

**Purpose.** Check the canonical skills, the JSON collateral, adapter parity, and a small blocklist of unsafe command patterns; CI runs it on every push to `main` and every pull request.

**Usage.**

```bash
python scripts/validate.py
```

**Reads.** `skills/*/SKILL.md`; `schemas/*.json`; `templates/project-config.example.json` and `templates/verification-plan.example.json`; the output of `scripts/sync_adapters.py --check`, which it runs as a subprocess; and, for the blocklist scan, every file directly under `scripts/` except `validate.py` itself plus `skills/*/SKILL.md`.

**Checks**, in order:

1. Each `skills/<name>/SKILL.md` starts with YAML frontmatter delimited by `---` lines (matched with a regex); its `name` field equals the directory name; the text contains each of `## Purpose`, `## Inputs`, `## Workflow`, `## Checks`, `## Deliverables`, `## Evidence Gate`, `## Stop Conditions`, and `## Safety` as a case-sensitive substring; and the file is at least 1800 characters long.
2. No two skills share a `name`.
3. Every `schemas/*.json` file and the two templates parse as JSON.
4. `sync_adapters.py --check` exits 0 (adapter parity).
5. No scanned file matches any of the six case-insensitive regexes in the `unsafe` list (download tools, recursive force delete, a permission-bypass flag, Node's child-process module, and Python's shell-mode subprocess flag).

**Writes.** Nothing.

**Exit codes.** `0` with `Validation OK: <n> skills, <m> schemas, adapter parity confirmed.`; `1` with one `ERROR: ...` line per problem on stderr; `1` with a traceback for an uncaught exception (for example a `SKILL.md` that does not decode in the locale's encoding, audit F17).

**Known limitations.**

- No minimum count is enforced: with `skills/` and both adapter trees present, in parity, and holding no `SKILL.md`, or with `schemas/` empty, it reports `Validation OK: 0 skills, 0 schemas`. A missing or file-less `skills/` is caught only indirectly, by the `sync_adapters.py --check` step exiting `4` (audit F4).
- The schemas are parsed, not applied: no artifact, template, or example is validated against any schema (audit F6).
- The blocklist is a regex scan over a fixed file set (non-recursive `scripts/*` and `skills/*/SKILL.md`; `tests/`, `.github/`, `templates/`, and `orgs/` are not scanned; the exemption is by the basename `validate.py`) and is a lint, not a control (audit F7).
- Frontmatter fields other than `name` are not checked; `description` and `version` may be absent or arbitrary (audit F11).
- Files are read without an explicit encoding, that is in the locale's preferred encoding, so non-ASCII skill text could fail to decode on a host whose locale is not UTF-8; the skills at this checkout are ASCII-only (audit F17).
- `orgs/cupel/` is not inspected; run `python3 orgs/cupel/tools/validate_cupel.py` and `python3 orgs/cupel/tools/check_parity.py` separately.

## Version sources

`VERSION` is the single source of the stack version; `bootstrap.py` copies its content into `install-manifest.json` as `stack_version`. `pyproject.toml` (`version`), the newest release heading in `CHANGELOG.md`, and the `version` field in each skill's frontmatter are meant to agree with it (all read `0.1.0` at this checkout). No script or test checks that agreement (audit F19).

## Tests and CI

`python -m unittest discover -s tests -v` runs `tests/test_stack.py` (adapter match, JSON parse, bootstrap dry run and install into a temporary directory, runner `cwd` escape), `tests/test_fssafety.py`, and `tests/test_sync_adapters.py` (the audit F1 regression tests T1.1 to T1.6 and the fail-closed contracts); the two Windows junction tests are skipped on POSIX hosts. `.github/workflows/ci.yml` runs `validate.py` and the test suite on `ubuntu-latest` with Python 3.12, and a separate `windows-latest` job runs only the two junction tests and treats a skip as failure. A green run proves only those checks; Python 3.10 and 3.11 are within `requires-python` but are not exercised in CI (audit F16).
