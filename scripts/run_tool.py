#!/usr/bin/env python3
"""Run one approved tool entry of a project's ``.soc-dv/config.json`` without a shell (audit F3, F10, F15, F17).

Usage:
    python scripts/run_tool.py --config <project>/.soc-dv/config.json --tool <name> --dry-run
        validate the entry, print the execution plan (redacted argv, resolved executable, cwd, timeout, the NAMES
        of the environment variables that would be passed) and whether the config is approved; spawn nothing
    python scripts/run_tool.py --config <project>/.soc-dv/config.json --approve
        interactive: print every tool's argv/cwd/timeout and the config SHA-256, ask the operator to type its
        first 8 hex characters, then write the approval record (stdin must be a terminal)
    python scripts/run_tool.py --config <project>/.soc-dv/config.json --tool <name>
        execute the entry (requires an approval record for the exact config bytes) and write a run record
    --approval-dir <dir>   use <dir> instead of the per-user default approval store (see below)

Approval model (F3). Executing an entry requires an approval record whose file name and ``config_sha256`` field
both equal the SHA-256 of the config file's exact bytes. Records live OUTSIDE the project tree by default, in the
per-user configuration directory (``$XDG_CONFIG_HOME`` or ``~/.config`` on POSIX, ``%APPDATA%`` on Windows) under
``soc-dv/approvals/<sha256>.json``. A repository that ships ``.soc-dv/config.json`` therefore cannot ship a matching
approval next to it, and any change to the config bytes (even whitespace) produces a different hash, i.e. a config
without an approval. ``--approve`` writes a record only from an interactive terminal, after showing the operator
everything the record authorises. ``--dry-run`` needs no approval; it only reports whether one exists.

Argv contract (F3). ``argv`` is a non-empty list of non-empty, non-blank strings; ``argv[0]`` may not contain a
newline. When ANY element (basename, case-insensitive, with or without .exe/.cmd/.bat) names a shell or interpreter
(sh, bash, zsh, dash, ksh, fish, csh, tcsh, cmd, powershell, pwsh, python*, pypy*, ipython*, jython, perl*, ruby*,
php*, node, nodejs, deno, bun, lua*, luajit, tclsh*, wish*, Rscript, julia, osascript, expect; ``*`` = optional
version suffix such as perl5.36 or php8) no LATER element may be an inline-code switch (-c, -e, -eval, -Command,
-EncodedCommand, /c, /k, -execute; additionally ``-r`` after php and ``eval`` after deno). The rule is deliberately
position-independent so that exec wrappers (env, nice, nohup, timeout, stdbuf, setsid, xargs, sudo, doas, time,
ionice, chrt, taskset, flock, unbuffer) cannot hide an interpreter, and it fails closed: a value that merely equals
an interpreter name followed by such a switch is rejected too. ``python -m module`` and script files stay allowed.
This is a denylist: it stops a config from smuggling a command line through a JSON argv; it does not stop an
interpreter from running a script file, which is the reviewable form.

Environment (F3, F17). The child starts from an EMPTY environment. Names in ``environment_allowlist`` are copied
from the parent, except that a name matching ``(?i)token|secret|passw|key|credential|cookie|auth`` is never passed
even when allowlisted (denied names are listed on stderr; values are never printed anywhere). PATH is passed only
when allowlisted; otherwise the child gets ``os.defpath`` and a notice is printed. On Windows the OS-essential
variables SYSTEMROOT, SYSTEMDRIVE, WINDIR, COMSPEC, PATHEXT, TEMP and TMP are always passed when present. A bare
``argv[0]`` is resolved with ``shutil.which`` against the CHILD's PATH; an absolute path is accepted as is; a
relative path must resolve inside the project root. The resulting absolute path is what is spawned and recorded
(symbolic links are left to the OS so that argv[0]-dependent multi-call binaries keep working; the link target is
recorded as ``executable_realpath``). Argv elements shaped ``<...token|secret|passw|key|credential|cookie...>=<value>``
(or ``:``) are printed and recorded with the value replaced by ``<redacted>``.

Run records (F10). Every execution writes ``<project root>/.soc-dv/runs/<run_id>/result.json``, ``stdout.log`` and
``stderr.log`` (child output is redirected there as bytes; stdin is /dev/null), also when the child times out or
cannot be started. The child runs in its own session (POSIX) or process group (Windows); on timeout or Ctrl-C the
whole group is terminated (SIGTERM, grace period, SIGKILL on POSIX; ``taskkill /T /F`` then kill on Windows).

Exit codes (stable):
    0      success (child returned 0), --dry-run, or approval record written
    1      unexpected environment failure (for example no resolvable home directory)
    2      unknown tool, or command-line usage error
    3      argv contract violation (shape, blank element, NUL, newline, interpreter with an inline-code switch)
    4      tool cwd escapes the project root, or is not an existing directory at execution time
    5      malformed config: unreadable, not UTF-8, invalid JSON, wrong type, timeout outside 1..max_timeout_seconds
    6      config not approved: no valid approval record for these exact bytes (the --approve command is printed)
    7      approval refused: stdin is not a terminal, or the typed confirmation did not match
    8      executable not resolvable (bare name not on the child's PATH, relative path outside the root, missing or
           not executable), or the process could not be started (recorded in result.json)
    9      run-record or approval-record I/O failure
    124    child timed out; its process group was terminated
    130    interrupted (Ctrl-C); the child's process group was terminated
    128+N  child killed by signal N (POSIX)
    N      otherwise the child's own return code (a value that collides with a runner code above is disambiguated
           by result.json, which records return_code, status and exit_code)

Residual risks (documented, not closed here): approved tools run unsandboxed with full user privilege (TB6).
H4 PATH hijack: an allowlisted PATH containing ``.`` or a writable directory redirects a bare ``argv[0]``, and on
Windows ``os.defpath`` itself contains ``.``; the resolved executable is recorded so the choice is at least
auditable, and a fallback to ``os.defpath`` may select a different tool version than the operator's shell would.
H1 TOCTOU between the cwd/executable checks and the spawn. The interpreter-switch denylist cannot enumerate every
way an interpreter accepts code (script files, stdin, PowerShell switch abbreviations). ``.bat``/``.cmd`` targets on
Windows are argument-quoted by the OS with rules unlike POSIX argv. Redaction is pattern based and covers only
``name=value`` style elements, and the environment name denylist also rejects harmless names (for example AUTHOR).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import getpass
import hashlib
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNKNOWN_TOOL = 2
EXIT_ARGV = 3
EXIT_CWD = 4
EXIT_CONFIG = 5
EXIT_UNAPPROVED = 6
EXIT_APPROVAL_REFUSED = 7
EXIT_EXECUTABLE = 8
EXIT_RUN_RECORD = 9
EXIT_TIMEOUT = 124
EXIT_INTERRUPTED = 130

SCHEMA_VERSION = "1.0"
DEFAULT_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_TIMEOUT_SECONDS = 86400
GRACE_SECONDS = 5.0
KILL_WAIT_SECONDS = 30.0
APPROVAL_SUBDIR = Path("soc-dv") / "approvals"
RUNS_SUBDIR = Path(".soc-dv") / "runs"
IS_WINDOWS = sys.platform == "win32"

ENV_DENY_RE = re.compile(r"(?i)token|secret|passw|key|credential|cookie|auth")
# Wider than the audit's ``<keyword>\s*[=:]\s*\S+`` so that ``--password=x``, ``passwd=x`` and ``api_key=x`` are
# caught too (the keyword may carry a suffix before the separator).
REDACT_RE = re.compile(r"(?i)((?:token|secret|passw|key|credential|cookie)[a-z0-9_-]*\s*[=:]\s*)\S+")
# Anchored, exact names (after lower-casing and stripping .exe/.cmd/.bat); ``[0-9.]*`` admits version suffixes such
# as perl5.36, ruby3.2, php8, tclsh8.6 or pypy3.10.
INTERPRETER_RE = re.compile(
    r"^(?:sh|bash|zsh|dash|ksh|fish|csh|tcsh|cmd|powershell|pwsh"
    r"|python[0-9]*(?:\.[0-9]+)?|pypy[0-9.]*|ipython[0-9.]*|jython"
    r"|perl[0-9.]*|ruby[0-9.]*|php[0-9.]*|node|nodejs|deno|bun|lua[0-9.]*|luajit|tclsh[0-9.]*|wish[0-9.]*"
    r"|rscript|julia|osascript|expect)$")
INTERPRETER_SUFFIXES = (".exe", ".cmd", ".bat")
INLINE_CODE_SWITCHES = frozenset({"-c", "-e", "-eval", "-command", "-encodedcommand", "/c", "/k", "-execute"})
# Inline-code switches that only one interpreter family uses unambiguously; deliberately not in the generic set.
INTERPRETER_EXTRA_SWITCHES = {"php": frozenset({"-r"}), "deno": frozenset({"eval"})}
WINDOWS_ESSENTIAL_ENV = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")


class RunToolError(Exception):
    """Base class; ``exit_code`` is the documented process exit status, ``label`` the ``ERROR[<label>]`` tag."""

    exit_code = EXIT_ERROR
    label = "error"


class UnknownToolError(RunToolError):
    exit_code = EXIT_UNKNOWN_TOOL
    label = "unknown-tool"


class ArgvError(RunToolError):
    exit_code = EXIT_ARGV
    label = "argv"


class CwdError(RunToolError):
    exit_code = EXIT_CWD
    label = "cwd"


class ConfigError(RunToolError):
    exit_code = EXIT_CONFIG
    label = "config"


class UnapprovedError(RunToolError):
    exit_code = EXIT_UNAPPROVED
    label = "unapproved"


class ApprovalRefusedError(RunToolError):
    exit_code = EXIT_APPROVAL_REFUSED
    label = "approval-refused"


class ExecutableError(RunToolError):
    exit_code = EXIT_EXECUTABLE
    label = "executable"


class RunRecordError(RunToolError):
    exit_code = EXIT_RUN_RECORD
    label = "run-record"


# --------------------------------------------------------------------------------------------------------------
# small helpers


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(ts: _dt.datetime) -> str:
    return ts.isoformat(timespec="seconds").replace("+00:00", "Z")


def _notice(message: str) -> None:
    print(f"notice: {message}", file=sys.stderr)


def _type_name(value) -> str:
    return "null" if value is None else type(value).__name__


def _short(value) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _norm_env_name(name: str) -> str:
    return name.upper() if IS_WINDOWS else name


def _cmdline(parts: list[str]) -> str:
    return subprocess.list2cmdline(parts) if IS_WINDOWS else shlex.join(parts)


def redact(argv: list[str]) -> list[str]:
    """Replace the value part of ``...token=value``-style elements; used for everything printed or recorded."""
    return [REDACT_RE.sub(r"\g<1><redacted>", element) for element in argv]


# --------------------------------------------------------------------------------------------------------------
# config (F15)


def load_config(path: Path) -> tuple[dict, bytes]:
    """Read the config bytes (they are what the approval binds), decode as UTF-8, parse and type-check."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"config {path} is not UTF-8: {exc}") from exc
    try:
        cfg = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"config {path} is not valid JSON: {exc}") from exc
    validate_config(cfg, path)
    return cfg, raw


def max_timeout(cfg: dict) -> int:
    return cfg.get("max_timeout_seconds", DEFAULT_MAX_TIMEOUT_SECONDS)


def effective_timeout(cfg: dict, entry: dict) -> int:
    return entry.get("timeout_seconds", min(DEFAULT_TIMEOUT_SECONDS, max_timeout(cfg)))


def validate_config(cfg, path: Path) -> None:
    """Whole-config type checks (exit 5). argv contents are checked per tool by ``check_argv`` (exit 3)."""
    where = f"config {path}"
    if not isinstance(cfg, dict):
        raise ConfigError(f"{where}: top level must be a JSON object, got {_type_name(cfg)}")
    tools = cfg.get("tools")
    if not isinstance(tools, dict):
        raise ConfigError(f"{where}: 'tools' must be an object of tool entries, got {_type_name(tools)}")
    limit = max_timeout(cfg)
    if not _is_int(limit) or limit < 1:
        raise ConfigError(f"{where}: 'max_timeout_seconds' must be a positive integer, got {_short(limit)}")
    allow = cfg.get("environment_allowlist", [])
    if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
        raise ConfigError(f"{where}: 'environment_allowlist' must be a list of non-empty strings")
    for name, entry in tools.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: tools.{name} must be an object, got {_type_name(entry)}")
        cwd = entry.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd:
            raise ConfigError(f"{where}: tools.{name}.cwd must be a non-empty string, got {_type_name(cwd)}")
        timeout = effective_timeout(cfg, entry)
        if not _is_int(timeout) or not 1 <= timeout <= limit:
            raise ConfigError(f"{where}: tools.{name}.timeout_seconds must be an integer in 1..{limit}, "
                              f"got {_short(timeout)}")


# --------------------------------------------------------------------------------------------------------------
# argv and cwd contracts (F3)


def _interpreter_name(argv0: str) -> str | None:
    name = argv0.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in INTERPRETER_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name if INTERPRETER_RE.match(name) else None


def _interpreter_family(name: str) -> str:
    """``php8.1`` -> ``php``, ``perl5.36`` -> ``perl``: the key into INTERPRETER_EXTRA_SWITCHES."""
    return re.sub(r"[0-9.]+$", "", name)


def check_argv(tool: str, argv) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise ArgvError(f"tools.{tool}.argv must be a non-empty list of strings, got {_type_name(argv)}")
    for index, element in enumerate(argv):
        if not isinstance(element, str):
            raise ArgvError(f"tools.{tool}.argv[{index}] must be a string, got {_type_name(element)}")
        if not element.strip():
            raise ArgvError(f"tools.{tool}.argv[{index}] is empty or whitespace-only")
        if "\x00" in element:
            raise ArgvError(f"tools.{tool}.argv[{index}] contains a NUL byte")
    if "\n" in argv[0] or "\r" in argv[0]:
        raise ArgvError(f"tools.{tool}.argv[0] contains a newline")
    # Position-independent on purpose: exec wrappers (env, nice, timeout, xargs, setsid, ...) cannot hide an
    # interpreter, and a plain value equal to an interpreter name is treated the same way (fail closed).
    for index, element in enumerate(argv):
        interpreter = _interpreter_name(element)
        if interpreter is None:
            continue
        blocked = INLINE_CODE_SWITCHES | INTERPRETER_EXTRA_SWITCHES.get(_interpreter_family(interpreter), frozenset())
        for later in argv[index + 1:]:
            if later.lower() in blocked:
                raise ArgvError(f"tools.{tool}.argv[{index}] names the interpreter '{interpreter}' and a later "
                                f"element is the inline-code switch '{later}'; put the code in a script file "
                                "inside the project instead")
    return list(argv)


def resolve_cwd(root: Path, tool: str, entry: dict) -> Path:
    cwd = (root / entry.get("cwd", ".")).resolve()
    try:
        cwd.relative_to(root)
    except ValueError:
        raise CwdError(f"tools.{tool}.cwd resolves to {cwd}, outside the project root {root}") from None
    return cwd


# --------------------------------------------------------------------------------------------------------------
# environment and executable resolution (F3, F17, H4)


def build_environment(cfg: dict) -> tuple[dict[str, str], list[str], bool]:
    """Default-deny child environment. Returns (env, denied allowlisted names, PATH taken from the parent)."""
    env: dict[str, str] = {}
    denied: set[str] = set()
    path_allowlisted = False
    for name in cfg.get("environment_allowlist", []):
        if _norm_env_name(name) == "PATH":
            path_allowlisted = True
            continue
        if ENV_DENY_RE.search(name):
            denied.add(name)
            continue
        value = os.environ.get(name)
        if value is not None:
            env[_norm_env_name(name)] = value
    parent_path = os.environ.get("PATH")
    path_from_parent = path_allowlisted and parent_path is not None
    env["PATH"] = parent_path if path_from_parent else os.defpath
    if IS_WINDOWS:
        for name in WINDOWS_ESSENTIAL_ENV:
            value = os.environ.get(name)
            if value is not None:
                env[name] = value
    return env, sorted(denied), path_from_parent


def _in_path_dirs(directory: Path, search_path: str) -> bool:
    wanted = os.path.normcase(os.path.abspath(str(directory)))
    for entry in search_path.split(os.pathsep):
        if entry and os.path.normcase(os.path.abspath(entry)) == wanted:
            return True
    return False


def resolve_executable(argv0: str, cwd: Path, root: Path, child_path: str) -> Path:
    """Return the absolute path that will be spawned. Absolute path: accepted. Relative path with a separator:
    joined to the tool cwd and required to resolve inside the project root. Bare name: looked up on the CHILD's
    PATH only (a hit outside those directories is discarded). Symbolic links are not replaced in the returned
    path, so argv[0]-dependent tools (multi-call binaries, version shims) behave as they would from a shell."""
    given = Path(argv0)
    explicit = given.is_absolute() or "/" in argv0 or (IS_WINDOWS and "\\" in argv0)
    if not explicit:
        found = shutil.which(argv0, path=child_path)
        if found is None or not _in_path_dirs(Path(found).parent, child_path):
            raise ExecutableError(f"'{argv0}' was not found on the child's PATH; allowlist PATH, install the tool, "
                                  "or give an explicit path")
        return Path(os.path.abspath(found))
    candidate = given if given.is_absolute() else cwd / given
    if not given.is_absolute():
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            raise ExecutableError(f"relative executable '{argv0}' resolves to {candidate.resolve()}, outside the "
                                  f"project root {root}") from None
    if not candidate.is_file():
        raise ExecutableError(f"executable '{argv0}' ({candidate}) is not an existing file")
    if not IS_WINDOWS and not os.access(candidate, os.X_OK):
        raise ExecutableError(f"executable '{argv0}' ({candidate}) is not executable")
    return candidate


# --------------------------------------------------------------------------------------------------------------
# approval records (F3)


def default_approval_dir() -> Path:
    try:
        if IS_WINDOWS:
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        else:
            xdg = os.environ.get("XDG_CONFIG_HOME")
            base = xdg if xdg and os.path.isabs(xdg) else str(Path.home() / ".config")
    except RuntimeError as exc:  # Path.home() cannot determine the home directory
        raise RunToolError(f"cannot determine the per-user approval directory: {exc}; use --approval-dir") from exc
    return Path(base) / APPROVAL_SUBDIR


def approval_status(record_path: Path, sha: str) -> tuple[bool, str]:
    """(approved, reason) for the record that must bind these exact config bytes."""
    if not record_path.is_file():
        return False, f"no approval record at {record_path}"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return False, f"approval record {record_path} is unreadable: {exc}"
    if not isinstance(record, dict) or record.get("config_sha256") != sha:
        return False, f"approval record {record_path} does not bind this config's SHA-256"
    return True, "approved"


def _approver() -> str:
    try:
        return getpass.getuser()
    except Exception:  # getpass raises OSError/KeyError/ImportError depending on the platform
        return "unknown"


def _write_json_atomically(path: Path, payload: dict, *, private_dir: bool) -> None:
    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            if private_dir and not IS_WINDOWS:
                os.chmod(path.parent, 0o700)
        tmp = path.with_name(f".{path.name}.tmp-{secrets.token_hex(4)}")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError as exc:
        raise RunRecordError(f"cannot write {path}: {exc}") from exc


def approve(cfg: dict, config_path: Path, root: Path, sha: str, record_path: Path) -> int:
    tools = {}
    for name, entry in cfg["tools"].items():
        argv = check_argv(name, entry.get("argv"))
        cwd = resolve_cwd(root, name, entry)
        tools[name] = {"argv": redact(argv), "cwd": str(cwd), "timeout_seconds": effective_timeout(cfg, entry)}
    allow = list(cfg.get("environment_allowlist", []))
    denied = sorted({name for name in allow if ENV_DENY_RE.search(name) and _norm_env_name(name) != "PATH"})
    summary = {
        "config_path": str(config_path),
        "config_sha256": sha,
        "project_root": str(root),
        "tools": tools,
        "environment_allowlist": allow,
        "environment_denied": denied,
        "path_policy": "parent PATH when allowlisted, otherwise os.defpath",
        "approval_record": str(record_path),
    }
    print(json.dumps(summary, indent=2))
    if not sys.stdin.isatty():
        raise ApprovalRefusedError("--approve needs an interactive terminal on stdin (stdin is not a TTY); rerun the "
                                   "same command interactively and type the confirmation")
    prompt = f"Type the first 8 hex characters of the SHA-256 ({sha[:8]}) to approve, anything else to abort: "
    try:
        typed = input(prompt)
    except EOFError:
        raise ApprovalRefusedError("no confirmation entered; nothing approved") from None
    if typed.strip().lower() != sha[:8]:
        raise ApprovalRefusedError("confirmation did not match the config SHA-256; nothing approved")
    record = {
        "schema_version": SCHEMA_VERSION,
        "config_sha256": sha,
        "config_path": str(config_path),
        "approved_at": _iso(_utc_now()),
        "approved_by": _approver(),
        "tools": tools,
        "environment_allowlist": allow,
        "environment_denied": denied,
    }
    _write_json_atomically(record_path, record, private_dir=True)
    print(f"approved: record written to {record_path}")
    return EXIT_OK


# --------------------------------------------------------------------------------------------------------------
# execution and run records (F10, H6)


def git_commit(root: Path) -> str | None:
    """HEAD commit of the repository at ``root`` read from .git files (dir, worktree file, commondir, loose or
    packed refs); never invokes git; None when unavailable."""
    try:
        dot_git = root / ".git"
        if dot_git.is_file():
            text = dot_git.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            git_dir = (root / text[len("gitdir:"):].strip()).resolve()
        elif dot_git.is_dir():
            git_dir = dot_git
        else:
            return None
        common = git_dir
        commondir = git_dir / "commondir"
        if commondir.is_file():
            common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head if re.fullmatch(r"[0-9a-f]{40,64}", head) else None
        ref = head[4:].strip()
        loose = common / ref
        if loose.is_file():
            value = loose.read_text(encoding="utf-8").strip()
            return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else None
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2 and not line.startswith(("#", "^")) and parts[1].strip() == ref:
                    return parts[0]
        return None
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def create_run_dir(root: Path) -> tuple[str, Path]:
    runs = root / RUNS_SUBDIR
    for _ in range(5):
        run_id = f"{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        run_dir = runs / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_id, run_dir
        except FileExistsError:
            continue
        except OSError as exc:
            raise RunRecordError(f"cannot create run directory {run_dir}: {exc}") from exc
    raise RunRecordError(f"cannot allocate a unique run id under {runs}")


def _spawn_kwargs() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_quietly(proc: subprocess.Popen, timeout: float) -> bool:
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def terminate_group(proc: subprocess.Popen) -> None:
    """Terminate the child's whole process group (POSIX session / Windows process tree). Never raises."""
    if IS_WINDOWS:
        taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
        exe = str(taskkill) if taskkill.is_file() else shutil.which("taskkill")
        if exe:
            try:
                subprocess.run([exe, "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False,
                               timeout=KILL_WAIT_SECONDS)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.kill()
        except OSError:
            pass
        _wait_quietly(proc, KILL_WAIT_SECONDS)
        return
    # The child is the leader of its own session, so its pid is the process-group id. SIGKILL is sent to the
    # group even after the leader exited: members that ignored SIGTERM keep the group alive.
    for sig, wait in ((signal.SIGTERM, GRACE_SECONDS), (signal.SIGKILL, KILL_WAIT_SECONDS)):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
        _wait_quietly(proc, wait)


def execute(tool: str, argv: list[str], executable: Path, cwd: Path, env: dict[str, str], denied: list[str],
            timeout: int, root: Path, config_path: Path, sha: str, record_path: Path) -> int:
    run_id, run_dir = create_run_dir(root)
    result_path = run_dir / "result.json"
    print(f"run record: {run_dir}")
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "tool": tool,
        "argv": redact(argv),
        "resolved_executable": str(executable),
        "executable_realpath": str(executable.resolve()),
        "cwd": str(cwd),
        "project_root": str(root),
        "config_path": str(config_path),
        "config_sha256": sha,
        "approval_record": str(record_path),
        "git_commit": git_commit(root),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "environment": sorted(env),
        "environment_denied": denied,
        "timeout_seconds": timeout,
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
    }
    spawn_argv = [str(executable)] + argv[1:]
    started = _utc_now()
    clock = time.monotonic()
    status, return_code, timed_out, exit_code, error, pid = "error", None, False, EXIT_EXECUTABLE, None, None
    try:
        with open(run_dir / "stdout.log", "wb") as out, open(run_dir / "stderr.log", "wb") as err:
            try:
                proc = subprocess.Popen(spawn_argv, cwd=str(cwd), env=env, shell=False, stdin=subprocess.DEVNULL,
                                        stdout=out, stderr=err, **_spawn_kwargs())
            except OSError as exc:
                error = f"could not start {spawn_argv[0]}: {exc}"
            else:
                pid = proc.pid
                try:
                    return_code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    terminate_group(proc)
                    status, timed_out, exit_code = "timeout", True, EXIT_TIMEOUT
                    return_code = proc.returncode
                except KeyboardInterrupt:
                    terminate_group(proc)
                    status, exit_code = "interrupted", EXIT_INTERRUPTED
                    return_code = proc.returncode
                else:
                    if return_code == 0:
                        status, exit_code = "pass", EXIT_OK
                    elif return_code < 0:  # H6: signal death N -> 128+N instead of an opaque 256-N
                        status, exit_code = "fail", 128 - return_code
                    else:
                        status, exit_code = "fail", return_code
    except OSError as exc:
        error = f"cannot open the run logs under {run_dir}: {exc}"
        exit_code = EXIT_RUN_RECORD
    ended = _utc_now()
    record.update({
        "pid": pid,
        "started_at": _iso(started),
        "ended_at": _iso(ended),
        "duration_seconds": round(time.monotonic() - clock, 3),
        "return_code": return_code,
        "timed_out": timed_out,
        "status": status,
        "exit_code": exit_code,
        "error": error,
    })
    _write_json_atomically(result_path, record, private_dir=False)
    print(f"run result: status={status} return_code={return_code} exit_code={exit_code} record={result_path}")
    if error:
        if exit_code == EXIT_RUN_RECORD:
            raise RunRecordError(error)
        raise ExecutableError(error)
    return exit_code


# --------------------------------------------------------------------------------------------------------------
# entry point


def run(args: argparse.Namespace, cfg: dict, config_path: Path, root: Path, sha: str, record_path: Path,
        approval_dir: Path) -> int:
    entry = cfg["tools"].get(args.tool)
    if entry is None:
        raise UnknownToolError(f"'{args.tool}' is not defined under 'tools' in {config_path}")
    argv = check_argv(args.tool, entry.get("argv"))
    cwd = resolve_cwd(root, args.tool, entry)
    timeout = effective_timeout(cfg, entry)
    env, denied, path_from_parent = build_environment(cfg)
    if denied:
        _notice("environment variables denied by name and never passed to the child: " + ", ".join(denied))
    if not path_from_parent:
        _notice("PATH is not allowlisted (or unset in the parent); the child gets os.defpath")
    try:
        executable, resolve_error = resolve_executable(argv[0], cwd, root, env["PATH"]), None
    except ExecutableError as exc:
        executable, resolve_error = None, exc
    approved, reason = approval_status(record_path, sha)
    plan = {
        "tool": args.tool,
        "argv": redact(argv),
        "resolved_executable": None if executable is None else str(executable),
        "executable_realpath": None if executable is None else str(executable.resolve()),
        "cwd": str(cwd),
        "timeout_seconds": timeout,
        "environment": sorted(env),
        "environment_denied": denied,
        "path_from_parent": path_from_parent,
        "config_path": str(config_path),
        "config_sha256": sha,
        "approved": approved,
        "approval_record": str(record_path),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(plan, indent=2))
    if args.dry_run:
        if resolve_error is not None:
            _notice(f"dry-run: {resolve_error}")
        if not approved:
            _notice(f"dry-run: {reason}; execution would be refused until the config is approved")
        return EXIT_OK
    if not approved:
        hint = [sys.executable, str(Path(__file__).resolve()), "--config", str(config_path), "--approve"]
        if args.approval_dir:
            hint += ["--approval-dir", str(approval_dir)]
        raise UnapprovedError(f"{reason}; review the plan above, then approve interactively with: {_cmdline(hint)}")
    if resolve_error is not None:
        raise resolve_error
    if not cwd.is_dir():
        raise CwdError(f"tools.{args.tool}.cwd {cwd} is not an existing directory")
    return execute(args.tool, argv, executable, cwd, env, denied, timeout, root, config_path, sha, record_path)


def _dispatch(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    root = (config_path.parent.parent if config_path.parent.name == ".soc-dv" else config_path.parent).resolve()
    approval_dir = Path(args.approval_dir).expanduser().resolve() if args.approval_dir else default_approval_dir()
    cfg, raw = load_config(config_path)
    sha = hashlib.sha256(raw).hexdigest()
    record_path = approval_dir / f"{sha}.json"
    if args.approve:
        return approve(cfg, config_path, root, sha, record_path)
    return run(args, cfg, config_path, root, sha, record_path, approval_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an approved project tool without a shell, with a default-deny environment and a run record",
        epilog="Exit codes and the approval model are documented in the module docstring of this script.")
    parser.add_argument("--config", required=True, help="path to the project's .soc-dv/config.json")
    parser.add_argument("--tool", help="name of the entry under 'tools' to run (not with --approve)")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate, print the plan and approval state; spawn nothing")
    parser.add_argument("--approve", action="store_true",
                        help="interactively approve the exact bytes of --config for execution (stdin must be a TTY)")
    parser.add_argument("--approval-dir", metavar="DIR",
                        help="approval record directory (default: <user config dir>/soc-dv/approvals)")
    args = parser.parse_args(argv)
    if args.approve and (args.tool or args.dry_run):
        parser.error("--approve takes neither --tool nor --dry-run")
    if not args.approve and not args.tool:
        parser.error("--tool is required unless --approve is given")
    try:
        return _dispatch(args)
    except RunToolError as exc:
        print(f"ERROR[{exc.label}] {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("ERROR[interrupted] interrupted before the tool finished", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main())
