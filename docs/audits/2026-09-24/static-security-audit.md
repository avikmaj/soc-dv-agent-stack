# soc-dv-agent-stack v0.1.0 — Static Security Audit

Date: 2026-09-24
Scope: static review of uploaded Group 4 files, cross-checked against 01/02/03 files. Nothing executed or modified.
Selected skills: tooling review under the evidence contract; signoff-audit criteria for readiness only.

Tags: [O] Observed · [D] Derived · [H] Hypothetical · [N] Not assessable

---

## 1. Repository inventory

Uploaded (Group 4) [O]:

| Upload | Presumed repo path |
|---|---|
| 04-contributing.md | CONTRIBUTING.md |
| 04-roadmap.md | ROADMAP.md |
| 04-changelog.md | CHANGELOG.md |
| 04-script-bootstrap.py.txt | scripts/bootstrap.py |
| 04-script-run-tool.py.txt | scripts/run_tool.py |
| 04-script-sync-adapters.py.txt | scripts/sync_adapters.py |
| 04-script-validate.py.txt | scripts/validate.py |
| 04-test-stack.py.txt | tests/test_stack.py (inferred from `parents[1]`) |
| 04-ci-workflow.yml.txt | .github/workflows/*.yml |
| 04-pyproject.toml.txt | pyproject.toml |
| 04-gitignore.txt | .gitignore |

Context [O]: 01 evidence contract / methodology / security policy / architecture; 20 × `02-skill-*.md`; 03 schemas (4) + template (1).

Referenced by code but not uploaded [N]: `CLAUDE.md`, `AGENTS.md`, `VERSION`, `skills/<name>/SKILL.md` (canonical tree), `.claude/skills/`, `.agents/skills/`, `templates/project-config.example.json`, `templates/verification-plan.example.json`, `LICENSE`, and the security policy / threat model / evaluation framework claimed by CHANGELOG.

Consequence [D]: adapter parity, bootstrap success, and CI green status are Not assessable. The 02-skill files may be Project-knowledge copies, not the canonical `skills/` tree (see F5).

---

## 2. Trust-boundary model

| ID | Zone | Trust | Crossing |
|---|---|---|---|
| TB0 | Maintainer / approved requirements | Trusted | — |
| TB1 | Repo source at PR head (skills, scripts, tests, workflow) | Untrusted until reviewed at pinned commit | CI executes; contributors execute locally per CONTRIBUTING |
| TB2 | Adapters `.claude/`, `.agents/` | Derived from TB1, must be byte-identical | `sync_adapters.py` (destructive), `--check` |
| TB3 | Bootstrap target directory | Untrusted filesystem (existing files, symlinks) | `bootstrap.py` writes |
| TB4 | `.soc-dv/config.json` | Effective command authority; no approval marker | `run_tool.py` executes its `argv` |
| TB5 | Parent process environment | Secret-bearing | `environment_allowlist` |
| TB6 | Child EDA/tool processes | Full user privilege, no sandbox | `subprocess.run` |
| TB7 | CI runner / GITHUB_TOKEN | Fork PR code runs with read token | `pull_request` trigger |
| TB8 | Agent harness reading CLAUDE.md / AGENTS.md / skills in target | Prompt/control-plane surface | Bootstrap installs agent instructions into another project |

Key derived point [D]: TB4 and TB8 are the real security boundaries. `shell=False` protects argument parsing, not what runs. Bootstrap is a supply-chain channel that plants agent control-plane text into third-party projects.

---

## 3. Observed security findings

### F1 · High · scripts/sync_adapters.py · `sync()` → `shutil.rmtree(target)` follows symlinked parent

- Evidence [O]: `TARGETS=[ROOT/'.claude'/'skills', ROOT/'.agents'/'skills']`; `if target.exists(): shutil.rmtree(target)`; no symlink or containment check.
- Scenario [D]: PR commits `.agents` as a git symlink to `/home/<user>/.codex` (or `~/.claude`). Contributor follows CONTRIBUTING step 3; `rmtree` deletes `~/.codex/skills` outside the repo. `rmtree` refuses a symlinked final component, but not a symlinked parent.
- Existing mitigation [O]: CI runs only `--check` (non-destructive).
- Minimal patch: before destructive ops assert `target.resolve().is_relative_to(ROOT.resolve())` and no component from ROOT to target `is_symlink()`; copy to sibling temp dir, then swap via `os.replace`.
- Regression test: `test_sync_refuses_symlinked_adapter_parent` — symlink `.claude` to a temp dir with a canary; expect nonzero exit, canary intact.
- Residual risk: TOCTOU between check and rmtree (Low; same-user attacker).

### F2 · High · scripts/bootstrap.py · writes follow symlinks in target; dangling links bypass conflict detection

- Evidence [O]: conflict test `dst.exists() and digest(src)!=digest(dst)`; writes via `mkdir(parents=True)` + `shutil.copy2(src,dst)`; manifest via `write_text` with no check.
- Scenario [D]: user installs into a cloned third-party repo containing `.claude → ~/.claude` or dangling `CLAUDE.md → ~/.config/autostart/x.desktop`. `exists()` is False for a dangling link → no conflict → `copy2` creates the file at the link destination. Off-project write without `--force`, violating the "project-local" claim. With `--force`, existing symlinked files (e.g. `~/.bashrc`) are overwritten.
- Existing mitigation [O]: `safe_target` refuses home and `/`; existing differing regular files refused without `--force`.
- Minimal patch: reject any `dst` where the file or any parent up to `target` `is_symlink()`; use `os.path.lexists` for conflict detection; write via temp file + `os.replace` in the same directory (replaces the link, not its target). Apply to `install-manifest.json` too.
- Regression tests: `test_bootstrap_rejects_dangling_symlink`, `test_bootstrap_rejects_symlinked_parent`, `test_bootstrap_force_does_not_follow_symlink` — assert out-of-target canary untouched.
- Residual risk: TOCTOU; Windows junctions need `os.path.isjunction` (3.12+).

### F3 · High · scripts/run_tool.py · "approved" not enforced; config fully controls execution; env allowlist can export secrets

- Evidence [O]: `argv=t.get('argv')` validated only as non-empty string list; `env={k:v ... if k in allow}` with `allow` from the same config; `root` derived from the config's own location.
- Scenario [D]: repo ships `.soc-dv/config.json` with `{"argv":["bash","-c","…"]}` or `["/bin/rm","-rf","/work"]` and `environment_allowlist:["GITHUB_TOKEN","AWS_SECRET_ACCESS_KEY"]`. `shell=False` is irrelevant once `argv[0]` is an interpreter; cwd containment does not bound what the process touches. `argv` JSON is printed to stdout, potentially leaking secrets into logs.
- Existing mitigation [O]: default-deny env (empty allowlist passes nothing); cwd containment with `resolve()` (catches symlinked cwd); dry-run.
- Minimal patch: require an approval record (config SHA-256 in `.soc-dv/approved.json`, written only by an interactive `--approve`); reject interpreter `argv[0]` followed by `-c`/`-e`; hard-deny env names matching `(?i)token|secret|passw|key|credential|cookie` regardless of allowlist; redact matching values in printed argv.
- Regression tests: `test_runner_refuses_unapproved_config`, `test_runner_strips_secret_env_even_if_allowlisted`, `test_runner_rejects_interpreter_dash_c`.
- Residual risk: approved tools remain unsandboxed (inherent to EDA execution).

### F4 · Medium · scripts/validate.py, scripts/sync_adapters.py · validation fails open on empty/missing tree

- Evidence [O]: `for p in sorted((ROOT/'skills').glob(...))` yields nothing if `skills/` absent; same for schemas; `in_sync` with two empty dicts → True; output `Validation OK: 0 skills, 0 schemas`. `test_adapters_match` and `test_json` are vacuous in the same case.
- Scenario [D]: a botched move/rename deletes the canonical tree; CI stays green.
- Minimal patch: `skills.lock` (expected names) or `MIN_SKILLS=20`; error if `skills/` or `schemas/` missing or empty; `sync --check` errors if `SOURCE` missing.
- Regression test: `test_validate_fails_on_empty_skills` (copy repo to temp, remove `skills/`, expect exit 1).
- Residual risk: none significant.

### F5 · Medium (release blocker) · scripts/validate.py `required` list vs skill text

- Evidence [O]: `required` = `## Inputs`, `## Checks`, `## Evidence Gate`, `## Stop Conditions` (case-sensitive substring). Uploaded skills use `## Required inputs`, have no `## Checks`, and use `## Evidence gate`, `## Stop conditions`. CONTRIBUTING lists the validator's set.
- Derived: if the 02-skill files are canonical, all 20 fail with 4 errors each, and likely also fail `len(s)<1800` (estimated ~1.3–1.5 kB each, not measured). CI would be red, contradicting CHANGELOG "production-ready". If not canonical, Project knowledge has drifted from the repo. Either way [N] until `skills/` is provided.
- Minimal patch: choose one canonical heading set; anchored case-insensitive match `re.search(r'(?mi)^## inputs\s*$', s)`; replace raw length check with per-section non-empty checks.
- Regression tests: `test_validate_rejects_missing_section`, `test_validate_accepts_canonical_fixture`.

### F6 · Medium · schemas/*.json, scripts/validate.py · schemas cannot reject malformed artifacts

- Evidence [O]: `03-schema-*` are custom field lists, not JSON Schema — no types, no `required`, no `additionalProperties`, no enums except traceability `status` and waiver `categories`. `validate.py` only `json.loads`; no artifact is validated against any schema.
- Gaps [D]: regression-result lacks `command`, `report_path`, configuration hash (required by evidence contract); `status` has no enum. Traceability has no `failing` state (pressure to mark failing requirements `implemented`). Waiver `expiry` has no format; `status` no enum. `priority` undefined, so the P0/P1 signoff criterion is uncheckable. Requirement-ID uniqueness unenforced.
- Minimal patch: convert to JSON Schema 2020-12; stdlib mini-validator (keeps zero deps) or pinned/hashed `jsonschema` dev dependency; validate `templates/*.json` against their schemas in `validate.py`.
- Regression tests: `test_schema_rejects_missing_required`, `…_bad_enum`, `…_extra_field`, `…_duplicate_req_id`.

### F7 · Medium · scripts/validate.py · unsafe-pattern scan is a weak blocklist

- Evidence [O]: patterns only `curl`, `wget`, `rm -rf`, `--dangerously-skip-permissions`, `child_process`, `shell=True`; scope is non-recursive `scripts/*` + `skills/*/SKILL.md`; exempts any file named `validate.py`.
- Missed [D]: `shutil.rmtree` (already used in sync), `os.system`, `os.popen`, multi-line `shell=True`, `urllib`/`socket`/`http.client`, `pip install`, `git push`. `tests/`, `.github/`, templates, config never scanned.
- Minimal patch: AST-based scan flagging `os.system`, `os.popen`, `shell=` non-False, network modules, `rmtree`, with explicit per-file allowlist (`sync_adapters.py:rmtree`); scan all tracked files; exempt by path, not basename.
- Regression test: `test_validate_flags_os_system_in_subdir` (fixture).
- Residual risk: blocklists remain bypassable; treat as lint, not a control.

### F8 · Medium · scripts/bootstrap.py · `safe_target` denylist is minimal

- Evidence [O]: refuses only `== home` and `== /`.
- Allowed [D]: `/etc`, `/usr/local`, `~/.config`, `/home`, repo `ROOT` itself (crashes with `SameFileError`), `ROOT/skills` (pollutes canonical tree). On Windows, `Path('/').resolve()` is the current drive only; `D:\` passes.
- Minimal patch: require target exists and is a directory; refuse filesystem anchors (`p.anchor == str(p)`), home and its ancestors, ROOT and anything inside it; optionally require `.git` or explicit `--allow-non-repo`.
- Regression test: parameterized `test_bootstrap_refuses_root_home_self`.

### F9 · Medium · scripts/bootstrap.py · `--force` destroys user files without backup; manifest unconditionally clobbered

- Evidence [O]: `--force` → `copy2` over user `CLAUDE.md`/`AGENTS.md`; manifest records only post-install hashes.
- Scenario [D]: project's own agent instructions lost silently; no uninstall or rollback.
- Minimal patch: under `--force`, move existing file to `<name>.bak.<ts>`; record `previous_sha256` and backup path in manifest.
- Regression test: `test_bootstrap_force_creates_backup`.

### F10 · Medium · scripts/run_tool.py · timeout leaves grandchildren; no evidence capture

- Evidence [O]: `subprocess.run(..., timeout=...)` kills only the direct child; `TimeoutExpired` uncaught (traceback). No run ID, timestamp, tool version, stdout/stderr capture, or result record.
- Scenario [D]: orphaned simv/xrun hold licenses and disk. Runs produce no artifact citable under the evidence contract, so runner output can never support PASS.
- Minimal patch: POSIX `start_new_session=True` + `os.killpg` on timeout; Windows `CREATE_NEW_PROCESS_GROUP` + tree kill. Write `.soc-dv/runs/<run_id>/{result.json,stdout.log,stderr.log}` with argv, cwd, config SHA-256, git commit, start/end time, return code.
- Regression test: `test_runner_timeout_kills_process_group` (child forks a sleeper).

### F11 · Medium · skills frontmatter, scripts/validate.py · missing `description`

- Evidence [O]: frontmatter has only `name` and `version`; validator doesn't require `description`.
- Derived (harness-version dependent): Claude Code and Codex skill discovery key on `description`; skills may not trigger.
- Minimal patch: require non-empty `description` ≤1024 chars in `validate.py`; add one to each skill.
- Regression test: `test_validate_requires_description`.

### F12 · Medium · .gitignore · gaps for DV artifacts and secrets

- Evidence [O]: covers `*.vcd`, `*.fst`, `*.wlf`, `*.fsdb`, `*.ucdb`, `*.vdb/`, `*.key`, `*.pem`.
- Missing [D]:
  - Waveforms: `*.vpd`, `*.shm/`, `*.trn`, `*.dsn`
  - Simulator build dirs: `simv*`, `csrc/`, `*.daidir/`, `xcelium.d/`, `INCA_libs/`, `work/`
  - Tool logs/coverage: `verdiLog/`, `novas*`, `cov_work/`, `urgReport/`, `DVEfiles/`
  - Credentials: `*.p12`, `*.pfx`, `id_rsa*`, `.netrc`, `.pypirc`, `credentials*.json`
  - `.soc-dv/config.json` (internal tool paths, license hosts), `.soc-dv/install-manifest.json`
  - Python build output: `dist/`, `build/`, `*.egg-info/`
- Scenario [D]: confidential VCS/Xcelium waveforms or license config committed, contradicting 01-security-policy.
- Patch: add the entries above.
- Regression test: `test_gitignore_covers_required_patterns` (table-driven; `git check-ignore` in temp repo or pattern-list assertion).

### F13 · Medium · scripts/sync_adapters.py · `copytree` follows symlinks inside `skills/`

- Evidence [O]: `shutil.copytree(SOURCE,target)` with default `symlinks=False` dereferences.
- Scenario [D]: `skills/x/ref.md → ~/.ssh/id_ed25519` materialized as a regular file in both adapters, then committed. `validate.py` also reads it.
- Patch: reject any symlink under `SOURCE` in validate and sync.
- Regression test: `test_sync_rejects_symlink_in_source`.

### F14 · Low · scripts/sync_adapters.py, scripts/bootstrap.py · non-atomic operations leave partial state

- Evidence [O]: sync does `rmtree` then `copytree`; bootstrap copies files, then reads `VERSION` (uncaught `FileNotFoundError` → no manifest).
- Patch: sync via temp dir + swap; bootstrap preflight that all sources and `VERSION` exist before any write.
- Regression test: `test_bootstrap_preflight_missing_source_writes_nothing`.

### F15 · Low · scripts/run_tool.py · config input validation

- Evidence [O]: non-dict config or tool entry → `AttributeError`; non-numeric `timeout_seconds` → `ValueError`; zero/negative timeout accepted; `environment_allowlist` not type-checked.
- Effect: fails closed, but with traceback and no structured exit code.
- Patch: explicit type checks with distinct exit codes; timeout bounded 1..configured max.
- Regression test: parameterized `test_runner_rejects_malformed_config`.

### F16 · Low · .github/workflows · CI hardening

- Evidence [O]: `actions/checkout` default `persist-credentials: true`; no `timeout-minutes`, no `concurrency`; matrix `ubuntu-latest` × Python 3.12 only while `requires-python >=3.10`; ruff configured but never run.
- Positive [O]: actions SHA-pinned; `permissions: contents: read`; `pull_request`, not `pull_request_target` (fork code gets no secrets).
- Not assessable [N]: whether pinned SHAs map to genuine upstream releases (no version comments, no Dependabot config uploaded).
- Patch: `persist-credentials: false`; `timeout-minutes: 10`; matrix ubuntu/windows/macos × 3.10/3.12; `# vX.Y.Z` comments on pins; Dependabot for `github-actions`; `ruff check` step only if ruff is pinned/hashed, otherwise drop the config.

### F17 · Low · multiple · Windows portability

- `validate.py` frontmatter regex requires `\n`; `core.autocrlf=true` checkouts fail all skills [D].
- `read_text()` without `encoding='utf-8'` → `UnicodeDecodeError` under cp1252 on non-ASCII, uncaught for skills [D].
- `run_tool` env lacks `SYSTEMROOT`/`PATHEXT`, breaking most Windows executables [D].
- `rmtree` fails on read-only files with no `onerror` [D].
- Drive-root check: see F8.
- Patch: `.gitattributes` `* text=auto eol=lf`; `encoding='utf-8'` everywhere; normalize `\r\n` before regex; always pass OS-essential env vars, explicit `PATH` handling on both platforms.
- Regression tests: `test_validate_accepts_crlf_skill`; Windows CI leg.

### F18 · Low · scripts/bootstrap.py · installs from adapters without parity check; SKILL.md only

- Evidence [O]: sources globbed from `.claude/skills`, not `skills/`; only `*/SKILL.md`.
- Scenario [D]: drifted adapter content shipped; future skill subfiles (`references/`, scripts) silently dropped.
- Patch: run `sync_adapters --check` logic as bootstrap preflight; copy whole skill directories subject to F2 guards.

### F19 · Informational · CHANGELOG, pyproject, CONTRIBUTING · release and documentation accuracy

- Version sources [O]: `VERSION` [N], pyproject `0.1.0`, CHANGELOG `0.1.0`, each skill `version: 0.1.0`. No check ties them together.
- "Production-ready" [D]: CHANGELOG (2026-09-24) claim contradicts the roadmap's own 1.0 criteria (independent security review, signed releases, SBOM) and the evidence contract.
- Unverifiable [N]: CHANGELOG claims threat model and evaluation framework, not uploaded. No `LICENSE` uploaded despite `license = MIT`.
- Destructive step undocumented [D]: CONTRIBUTING step 3 (sync) deletes adapter trees (F1) without warning.
- Patch: single-source version from `VERSION`, validate asserts agreement with pyproject, CHANGELOG head, skill versions; reword to "initial foundation (pre-release)"; document that sync deletes and rewrites adapter trees.

### Negative results (clean) [O]

- No `shell=True`, `os.system`, or `popen` anywhere.
- No network calls in scripts.
- No package installation.
- No git/GitHub operations.
- No secrets in uploaded files.
- `validate.py` subprocess call is an argv list with `sys.executable`.
- `run_tool` cwd containment correctly rejects `..`, absolute paths, and symlinked escapes (resolves before `relative_to`).
- Bootstrap defaults to no-overwrite, supports dry-run, never overwrites an existing `config.json`.

---

## 4. Hypothetical risks

- H1 · TOCTOU: symlink swap between check and write in bootstrap, sync, and run_tool cwd. Requires same-user attacker with concurrent access.
- H2 · pathlib recursion (Python ≤3.12): `rglob` in `files()` may traverse symlinked directories, making `--check` compare out-of-tree content or loop. Version-dependent.
- H3 · Planted instructions: compromised upstream `CLAUDE.md`/`AGENTS.md` installed by bootstrap becomes agent control-plane text in the victim project (TB8). No signature or hash pinning of the stack.
- H4 · PATH hijack: if `PATH` is allowlisted and contains `.` or a writable dir, `argv[0]` lookup can be redirected. If `PATH` is absent, fallback to `os.defpath` may silently select a different tool version, breaking evidence reproducibility.
- H5 · Unverifiable action pins: pinned SHAs could be non-release commits.
- H6 · Signal exit codes: child killed by signal → negative return code → `SystemExit(-N)` → exit 256−N. Harmless but opaque to regression wrappers.

---

## 5. Test-gap analysis

Existing [O]:
- `test_adapters_match` — one-directional, vacuous on empty tree.
- `test_json` — parse only.
- `test_bootstrap_dry_run`.
- `test_bootstrap_install` — happy path; no hash check, no out-of-target write check.
- `test_runner_rejects_escape` — `..` only.
- Unused `hashlib` import.

Missing negative tests:

| Area | Missing tests |
|---|---|
| sync | symlinked adapter parent (F1); symlink in source (F13); `--check` detects extra/missing/diff adapter file; missing `skills/` fails |
| bootstrap | dangling/parent/forced symlink (F2); refuse root, home, drive root, self, inside-ROOT (F8); conflict without `--force` exits 3 with file intact; `--force` backup (F9); preflight missing source writes nothing (F14); installed hashes match manifest; no writes outside target (tree snapshot diff) |
| run_tool | unknown tool → 2; bad argv shapes → 3; absolute/symlinked cwd → 4; env filtering (non-allowlisted var absent in child); secret-name denial (F3); malformed config/timeout (F15); timeout kills process group (F10); dry-run spawns nothing |
| validate | missing section, name mismatch, missing frontmatter, duplicate names, invalid JSON, drift, unsafe pattern, empty tree (F4/F5/F7/F11); CRLF and UTF-8 fixtures (F17) |
| schemas | missing required field, wrong type, bad enum, extra field, duplicate requirement ID (F6) |
| release | version agreement (F19) |

CI coverage [D]: none of the security-critical negative paths are exercised except the single cwd `..` case.

---

## 6. Prioritized remediation plan

P0 — release blockers:
1. F1: sync symlink/containment guard + atomic swap.
2. F2: bootstrap no-follow writes + `lexists` conflict detection.
3. F3: runner approval record, secret-env hard-deny, argv redaction.
4. F4 + F5: validation fails closed; reconcile section contract with canonical skills; supply `skills/` for parity assessment.
5. Negative tests for all of the above in CI.

P1:
- F6 real JSON Schema + template validation.
- F13 reject symlinks in `skills/`.
- F8 `safe_target` hardening.
- F9 backup under `--force`.
- F10 process-group kill + run-evidence records.
- F11 require `description`.
- F12 `.gitignore` additions.
- F7 AST-based scan.

P2:
- F16 CI hardening and OS/Python matrix.
- F17 portability fixes + `.gitattributes`.
- F14 + F15 robustness.
- F18 bootstrap parity preflight + full skill-dir copy.
- F19 single-source version + documentation corrections.

Human decisions needed:
- (a) Canonical heading set.
- (b) Zero-dependency stdlib schema validator vs pinned `jsonschema` dev dependency.
- (c) `run_tool` approval model: config hash in approval file vs interactive confirmation.
- (d) Whether bootstrap may target non-git directories.

---

## 7. Public-release readiness: NOT READY

Criteria not met:
- Three High findings allowing off-project deletion/writes or unapproved execution with secret export (F1–F3).
- Validation is failing or non-canonical (F5) and fails open (F4).
- Schemas enforce nothing (F6).
- No negative-path CI coverage.
- Canonical `skills/`, adapters, `VERSION`, templates, `LICENSE`, and a CI run log not provided; adapter parity and "CI green" are Unverified.
- CHANGELOG "production-ready" claim unsupported by evidence.

Path to CONDITIONAL:
- P0 closed.
- Negative tests added and passing with evidence: commit SHA, CI run ID, Python version per OS leg.
- Canonical tree uploaded so F5 and adapter parity move from Not assessable to Observed.

Status: awaiting approval before patch generation.
