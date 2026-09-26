# Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and on every pull request (audit findings F16 and F17). It
holds no gating logic of its own: every decision is made by `tests/ci_skip_policy.py`, which is unit-tested by
`tests/test_ci_skip_policy.py` and can be run locally. Hardening: `permissions: contents: read`, `persist-credentials:
false` on every checkout, `timeout-minutes: 15` on every job, and a `concurrency` group per workflow and pull request
(or ref) with `cancel-in-progress: true`.

## Matrix

| Job | Runner | Python | Proves |
|---|---|---|---|
| `validate` | ubuntu-latest | 3.10, 3.11, 3.12 | the reference platform: POSIX-only tests run, symbolic and hard links work, 3.10 is the oldest interpreter `pyproject.toml` allows |
| `validate` | macos-latest | 3.10, 3.12 | the same on a second POSIX platform (different `realpath`, temp-dir layout and userland) |
| `validate` | windows-latest | 3.10, 3.12 | the Windows-only tests execute (the four junction tests must report `ok`), POSIX-only tests skip, `TEMP`/`TMP` confined to the runner temp dir |
| `crlf-checkout` | windows-latest | 3.12 | with `core.autocrlf=true` set before checkout, `.gitattributes` still yields LF working copies and the whole sequence passes as on the matrix Windows legs |

`fail-fast: false`, so one red leg never hides the others. Every leg runs the same steps in order: checkout;
setup-python; `python scripts/validate.py`; `python scripts/schema_check.py --self-check`;
`python scripts/schema_check.py --templates`; `python scripts/sync_adapters.py --check`; a capability probe
(`python tests/ci_skip_policy.py --probe`: can this runner create a symbolic link, a hard link and, on Windows, a
junction? printed as evidence, never a failure); the full suite `python -m unittest discover -s tests -v` with its
complete output captured to `unittest.log` and its exit status to `unittest.rc`; the gate
`python tests/ci_skip_policy.py --platform "$RUNNER_OS" --log ... --rc ... --report ...`; and the evidence upload.
The `crlf-checkout` job additionally records `git ls-files --eol` before validation runs.

## Skip policy

The gate parses every `... skipped '<reason>'` line of the log, classifies the reason and applies this table.

| Reason class | Marker in the reason | Linux | macOS | Windows |
|---|---|---|---|---|
| windows-only | Windows, win32, junction, read-only attribute, drive roots, OS-essential | expected | expected | **fail** |
| posix-only | starts with `POSIX-only` | **fail** | **fail** | expected |
| junction-capability | `junction creation not permitted` | **fail** | **fail** | **fail** |
| symlink-capability | `cannot create symbolic links on this host` | **fail** | **fail** | warning (`::warning::` annotation); **fail** when `CI_REQUIRE_SYMLINKS=1` |
| hardlink-capability | `hard links unavailable on this host` | **fail** | **fail** | **fail** |
| line-endings | `checkout translated line endings` | **fail** | **fail** | **fail** (also in `crlf-checkout`) |
| unknown | anything else | **fail** | **fail** | **fail** |

Capability markers are matched before the platform words, so a junction-capability reason (which also says
"junction") and a POSIX-only reason (which may mention Windows) land in the right row. Independently of the skips the
verdict is FAIL when the unittest exit status is non-zero, the `Ran N tests` line or the `OK`/`FAILED` summary is
missing, the summary is `FAILED`, N is 0, or the number of skip lines found differs from the summary's `skipped=N`.
On Windows the four junction tests named in `REQUIRED_OK_ON_WINDOWS` (`test_fssafety`, `test_sync_adapters`,
`test_bootstrap` T2.3, `test_validate`) must additionally appear as `... ok`; this is the F1 guarantee the former
two-test Windows job gave, now enforced against the full suite, and no flag relaxes it.

Escape hatches: `--allow-reason <substring>` (repeatable, case-insensitive) marks matching skips ALLOWED so the
coordinator can relax one rule without editing code if a first run disproves an assumption; none is pre-set.
`CI_REQUIRE_SYMLINKS=1` (or `--require-symlinks`) turns the Windows symlink warning into a failure; the workflow
leaves it unset until a capability probe from windows-latest has shown that the runner can create symbolic links.

## The `crlf-checkout` job

`git config --global core.autocrlf true` runs before `actions/checkout`, so the result does not depend on the runner
image's git defaults. The job prints `git ls-files --eol` for `*.md`, `*.py`, `*.json`, `.gitattributes` and
`VERSION` (first 40 entries; the full listing and a listing of every tracked file are in the artifact) and then runs
the same validate / schema / sync / suite / gate sequence. A CRLF working copy shows up three ways: in the listing
(`w/crlf`), as a `validate.py` error, and as a `line-endings` skip that the gate fails.

## Artifacts

Uploaded with `if: always()`, so they exist for red legs too: `ci-evidence-<os>-py<python>` for every matrix leg
(for example `ci-evidence-windows-latest-py3.10`) and `ci-evidence-crlf-checkout-windows-latest-py3.12`. Each holds
`run-info.txt` (run, commit, git line-ending configuration, interpreter), `capability-probe.txt`, `unittest.log`,
`unittest.rc` and `ci-skip-policy-report.txt`; the CRLF job adds `ls-files-eol.txt` and `ls-files-eol-all.txt`.

## Dependabot

`.github/dependabot.yml` watches the `github-actions` ecosystem weekly (at most 5 open pull requests, commit prefix
`ci`). Every action is pinned to a full commit SHA; a SHA changes only by merging a Dependabot pull request, never by
hand. The Node.js 20 runtime deprecation warning printed for the current `actions/checkout` and
`actions/setup-python` pins is resolved by accepting those pull requests. There is no `pip` ecosystem entry because
the project has no dependencies.

## What a green run proves

Exactly what the listed steps check, on the listed runner images and interpreters, for the commit that was checked
out (`github.sha` is the merge commit on pull-request events; `run-info.txt` records both SHAs): the validators
exit 0, the templates match the schemas, the adapters are in parity, the full suite passes with only the skips the
table allows, and on Windows the junction tests ran. It proves nothing about other platforms, interpreters, shells or
filesystems, about the runner's symbolic-link privilege unless `CI_REQUIRE_SYMLINKS=1` is set, or about anything the
suite does not test. Read the artifacts, not the green tick, when a claim depends on it.

## Running the gate locally

```
python -m unittest discover -s tests -v > /tmp/unittest.log 2>&1; echo $? > /tmp/unittest.rc
python tests/ci_skip_policy.py --platform Linux --log /tmp/unittest.log --rc /tmp/unittest.rc
python tests/ci_skip_policy.py --probe
python -m unittest discover -s tests -p "test_ci_skip_policy.py" -v
```

Use `--platform Windows` or `--platform macOS` to evaluate a log captured on those platforms.
