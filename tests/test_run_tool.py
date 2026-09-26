"""Regression tests for scripts/run_tool.py: audit findings F3, F10, F15, F17 and notes H4/H6.

Run: python -m unittest tests.test_run_tool -v

Every test builds a throwaway project under a temporary directory (<tmp>/proj/.soc-dv/config.json), points the
runner at a temporary approval store with --approval-dir, and redirects XDG_CONFIG_HOME/APPDATA into the temporary
directory so the operator's real approval store is never read or written. The "tools" are small Python helper
SCRIPTS written into the temporary directory and started as ``<sys.executable> <script> ...``; no test passes
inline code to an interpreter, writes into the repository, or needs the network.

  F15  malformed configs -> exit 5, one-line ERROR[config], no traceback
  F3   unknown tool 2; argv contract 3 (shapes, interpreter inline-code switches); cwd escapes 4 (.., absolute, symlink)
  F3   approval: unapproved execution refused (6) with the --approve hint and no side effect; the approval binds the
       exact config bytes; --approve refused without a TTY or on a mismatch (7); interactive approval writes the record
  F3   environment: default deny, secret-named variables never passed even when allowlisted, values never printed,
       argv redaction in the plan and in result.json
  F17  PATH policy (os.defpath when not allowlisted), bare names resolved against the child's PATH, Windows essentials
  F10  run record (result.json, stdout.log, stderr.log); timeout terminates the whole process group (124);
       H6 signal deaths map to 128+N
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUN_TOOL = ROOT / "scripts" / "run_tool.py"
IS_WINDOWS = sys.platform == "win32"
EXIT_UNKNOWN_TOOL, EXIT_ARGV, EXIT_CWD, EXIT_CONFIG = 2, 3, 4, 5
EXIT_UNAPPROVED, EXIT_APPROVAL_REFUSED, EXIT_EXECUTABLE, EXIT_TIMEOUT = 6, 7, 8, 124

ENVDUMP_PY = ("import json, os, sys\n"
              "with open(sys.argv[1], 'w', encoding='utf-8') as fh:\n"
              "    json.dump(dict(os.environ), fh)\n")
MARKER_PY = ("import sys\n"
             "with open(sys.argv[1], 'w', encoding='utf-8') as fh:\n"
             "    fh.write('spawned\\n')\n")
EMIT_PY = ("import sys\n"
           "sys.stdout.write('OUT-LINE\\n')\n"
           "sys.stderr.write('ERR-LINE\\n')\n"
           "sys.exit(int(sys.argv[1]))\n")
PARENT_PY = ("import subprocess, sys, time\n"
             "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
             "time.sleep(60)\n")
GRANDCHILD_PY = ("import os, sys, time\n"
                 "with open(sys.argv[1], 'w', encoding='utf-8') as fh:\n"
                 "    fh.write(str(os.getpid()))\n"
                 "time.sleep(60)\n")
SELFKILL_PY = "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n"


def tool(argv, **extra) -> dict:
    entry = {"argv": argv}
    entry.update(extra)
    return entry


def config(tools, **top) -> dict:
    cfg = {"tools": tools}
    cfg.update(top)
    return cfg


def first_json(text: str):
    """The plan/summary object the runner prints first on stdout (later lines are progress messages)."""
    obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
    return obj


def symlink_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        case.skipTest(f"cannot create symbolic links on this host: {exc}")


def load_module():
    """Import scripts/run_tool.py in-process without leaving bytecode in the repository."""
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("run_tool_under_test", RUN_TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = saved
    return mod


def pid_gone(pid: int) -> bool:
    """True when the process no longer exists, or is a zombie waiting for PID 1 to reap it (dead either way)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
        return state == "Z"
    except (OSError, IndexError):
        return False


class Fixture:
    """A throwaway project with its own approval store and helper scripts, all under one temporary directory."""

    def __init__(self, tmp: Path):
        self.tmp = tmp.resolve()
        self.root = self.tmp / "proj"
        self.config_path = self.root / ".soc-dv" / "config.json"
        self.config_path.parent.mkdir(parents=True)
        self.approval_dir = self.tmp / "approvals"
        self.helpers = self.tmp / "helpers"
        self.helpers.mkdir()

    def write_config(self, cfg) -> None:
        data = cfg if isinstance(cfg, bytes) else json.dumps(cfg, indent=2).encode("utf-8")
        self.config_path.write_bytes(data)

    def sha(self) -> str:
        return hashlib.sha256(self.config_path.read_bytes()).hexdigest()

    def approve(self) -> Path:
        """Stand in for a completed interactive approval: a record binding the current config bytes."""
        self.approval_dir.mkdir(exist_ok=True)
        record = self.approval_dir / f"{self.sha()}.json"
        record.write_text(json.dumps({"schema_version": "1.0", "config_sha256": self.sha()}), encoding="utf-8")
        return record

    def script(self, name: str, body: str) -> str:
        path = self.helpers / name
        path.write_text(body, encoding="utf-8")
        return str(path)

    def run(self, *args: str, env: dict | None = None, approval_dir: bool = True,
            timeout: float = 60.0) -> subprocess.CompletedProcess:
        child_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", XDG_CONFIG_HOME=str(self.tmp / "xdg"),
                         APPDATA=str(self.tmp / "xdg"))
        child_env.update(env or {})
        cmd = [sys.executable, str(RUN_TOOL), "--config", str(self.config_path), *args]
        if approval_dir:
            cmd += ["--approval-dir", str(self.approval_dir)]
        return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=str(self.tmp),
                              env=child_env, timeout=timeout)

    def run_dirs(self) -> list:
        runs = self.root / ".soc-dv" / "runs"
        return sorted(runs.iterdir()) if runs.is_dir() else []

    def result(self) -> dict:
        dirs = self.run_dirs()
        assert len(dirs) == 1, dirs
        return json.loads((dirs[0] / "result.json").read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    """Exit codes 2, 3 and 4, in that order, before any approval check; --dry-run needs no approval."""

    def test_unknown_tool_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"lint": tool(["echo", "x"])}))
            r = fx.run("--tool", "nope", "--dry-run")
            self.assertEqual(r.returncode, EXIT_UNKNOWN_TOOL, r.stderr)
            self.assertIn("ERROR[unknown-tool]", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_bad_argv_shapes_exit_3(self):
        cases = {"missing": {}, "string": {"argv": "echo x"}, "empty list": {"argv": []},
                 "non-string element": {"argv": ["echo", 1]}, "empty element": {"argv": ["echo", ""]},
                 "blank element": {"argv": ["echo", "  "]}, "blank argv0": {"argv": [" ", "x"]},
                 "newline in argv0": {"argv": ["ec\nho", "x"]}, "NUL in element": {"argv": ["echo", "a\x00b"]}}
        for label, entry in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                fx = Fixture(Path(d))
                fx.write_config(config({"x": entry}))
                r = fx.run("--tool", "x", "--dry-run")
                self.assertEqual(r.returncode, EXIT_ARGV, f"{label}: {r.stdout}{r.stderr}")
                self.assertIn("ERROR[argv]", r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def _assert_argv_rejected(self, argv: list, switch: str) -> None:
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"x": tool(argv)}))
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, EXIT_ARGV, f"{argv}: {r.stdout}{r.stderr}")
            self.assertIn("ERROR[argv]", r.stderr)
            self.assertIn(f"'{switch}'", r.stderr, "the message names the rejected switch")
            self.assertEqual(r.stdout, "", "no plan may be printed for a rejected argv")

    def test_interpreter_inline_code_switch_exit_3(self):
        cases = [(["bash", "-c", "echo hi"], "-c"), (["/bin/sh", "-c", "id"], "-c"),
                 (["python3", "-c", "print(1)"], "-c"), (["python3.12", "-c", "x"], "-c"),
                 (["python", "-c", "x"], "-c"), (["pypy3", "-c", "x"], "-c"), (["pypy3.10", "-c", "x"], "-c"),
                 (["ipython3", "-c", "x"], "-c"), (["jython", "-c", "x"], "-c"),
                 (["C:\\Windows\\System32\\cmd.exe", "/c", "dir"], "/c"), (["cmd", "/K", "dir"], "/K"),
                 (["CMD.EXE", "/C", "dir"], "/C"), (["powershell", "-Command", "Get-Date"], "-Command"),
                 (["PowerShell.exe", "-EncodedCommand", "ZQB4AGkAdAA="], "-EncodedCommand"),
                 (["pwsh", "-c", "x"], "-c"), (["node", "-e", "1"], "-e"), (["nodejs", "-e", "1"], "-e"),
                 (["bun", "-e", "1"], "-e"), (["perl", "-e", "1"], "-e"), (["perl5.36", "-e", "1"], "-e"),
                 (["ruby", "-e", "1"], "-e"), (["ruby3.2", "-e", "1"], "-e"), (["lua", "-e", "x"], "-e"),
                 (["lua5.4", "-e", "x"], "-e"), (["luajit", "-e", "x"], "-e"), (["zsh", "-c", "x"], "-c"),
                 (["dash", "-c", "x"], "-c"), (["ksh", "-c", "x"], "-c"), (["fish", "-c", "x"], "-c"),
                 (["csh", "-c", "x"], "-c"), (["tcsh", "-c", "x"], "-c"), (["wish", "-c", "x"], "-c"),
                 (["tclsh8.6", "-c", "x"], "-c"), (["Rscript", "-e", "1"], "-e"), (["julia", "-e", "1"], "-e"),
                 (["osascript", "-e", "x"], "-e"), (["expect", "-c", "x"], "-c"), (["php8.1", "-r", "x"], "-r"),
                 (["deno", "eval", "x"], "eval"), (["python3", "script.py", "-c", "cfg"], "-c")]
        for argv, switch in cases:
            with self.subTest(argv=argv):
                self._assert_argv_rejected(argv, switch)

    def test_exec_wrappers_cannot_hide_interpreter_exit_3(self):
        cases = [(["env", "python3", "-c", "code"], "-c"), (["/usr/bin/env", "bash", "-c", "code"], "-c"),
                 (["timeout", "10", "sh", "-c", "code"], "-c"), (["nice", "-n", "5", "perl", "-e", "code"], "-e"),
                 (["xargs", "sh", "-c", "code"], "-c"), (["stdbuf", "-o0", "node", "-e", "code"], "-e"),
                 (["setsid", "pwsh", "-Command", "x"], "-Command"), (["php", "-r", "code"], "-r"),
                 (["deno", "eval", "code"], "eval"), (["env", "php8", "-r", "code"], "-r"),
                 (["sudo", "-u", "eda", "deno", "eval", "code"], "eval"),
                 (["mytool", "--lang", "python", "-c", "x"], "-c")]  # value equal to an interpreter: fail closed
        for argv, switch in cases:
            with self.subTest(argv=argv):
                self._assert_argv_rejected(argv, switch)

    def test_interpreter_module_and_script_forms_stay_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            allowed = {"mod": [sys.executable, "-m", "json.tool", "--help"],
                       "script": [sys.executable, fx.script("noop.py", "pass\n")],
                       "plain": ["verilator", "--lint-only", "-Wall", "-f", "files.f"],
                       "wrapped_script": ["env", "python3", "tool.py", "--flag"],
                       "wrapped_make": ["timeout", "10", "make", "-C", "sim", "smoke"],
                       "node_require": ["node", "-r", "ts-node/register", "script.ts"],
                       "ruby_require": ["ruby", "-r", "json", "script.rb"],
                       "php_file": ["php", "-f", "tool.php"],
                       "deno_run": ["deno", "run", "script.ts"]}
            fx.write_config(config({name: tool(argv) for name, argv in allowed.items()}))
            for name in allowed:
                r = fx.run("--tool", name, "--dry-run")
                self.assertEqual(r.returncode, 0, f"{name}: {r.stdout}{r.stderr}")

    def test_cwd_escape_exit_4(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            outside = fx.tmp / "outside"
            outside.mkdir()
            for label, cwd in (("dotdot", "../outside"), ("absolute", str(outside)), ("dotdot-root", "../../")):
                with self.subTest(label):
                    fx.write_config(config({"x": tool(["echo", "x"], cwd=cwd)}))
                    r = fx.run("--tool", "x", "--dry-run")
                    self.assertEqual(r.returncode, EXIT_CWD, f"{label}: {r.stdout}{r.stderr}")
                    self.assertIn("ERROR[cwd]", r.stderr)
                    self.assertEqual(r.stdout, "", "no plan may be printed for an escaping cwd")
            (fx.root / "sim").mkdir()
            fx.write_config(config({"x": tool(["echo", "x"], cwd="sim")}))
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(first_json(r.stdout)["cwd"], str(fx.root / "sim"))

    def test_cwd_escape_via_symlink_exit_4(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            outside = fx.tmp / "outside"
            outside.mkdir()
            symlink_or_skip(self, outside, fx.root / "link")
            fx.write_config(config({"x": tool(["echo", "x"], cwd="link")}))
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, EXIT_CWD, r.stderr)
            self.assertIn("ERROR[cwd]", r.stderr)
            self.assertIn(str(outside), r.stderr)

    def test_check_order_unknown_tool_then_argv_then_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"x": {"argv": "bad", "cwd": "../../"}}))
            self.assertEqual(fx.run("--tool", "y", "--dry-run").returncode, EXIT_UNKNOWN_TOOL)
            self.assertEqual(fx.run("--tool", "x", "--dry-run").returncode, EXIT_ARGV)
            fx.write_config(config({"x": tool(["echo", "x"], cwd="../../")}))
            self.assertEqual(fx.run("--tool", "x", "--dry-run").returncode, EXIT_CWD)
            self.assertEqual(fx.run("--tool", "x").returncode, EXIT_CWD, "structural checks precede approval")


class ConfigValidationTests(unittest.TestCase):
    """F15: one distinct exit code and a one-line error for every malformed config."""

    def test_malformed_configs_exit_5(self):
        good = tool([sys.executable, "x.py"])
        cases = {
            "non-object top level": b"[1, 2, 3]",
            "tools not an object": {"tools": []},
            "tools missing": {"schema_version": "1.0"},
            "tool entry not an object": {"tools": {"x": "echo"}},
            "cwd not a string": {"tools": {"x": tool(["echo"], cwd=5)}},
            "timeout zero": {"tools": {"x": tool(["echo"], timeout_seconds=0)}},
            "timeout negative": {"tools": {"x": tool(["echo"], timeout_seconds=-1)}},
            "timeout bool": {"tools": {"x": tool(["echo"], timeout_seconds=True)}},
            "timeout string": {"tools": {"x": tool(["echo"], timeout_seconds="60")}},
            "timeout above max": {"tools": {"x": tool(["echo"], timeout_seconds=100)}, "max_timeout_seconds": 50},
            "timeout above default max": {"tools": {"x": tool(["echo"], timeout_seconds=86401)}},
            "max not an integer": {"tools": {"x": good}, "max_timeout_seconds": "1d"},
            "max zero": {"tools": {"x": good}, "max_timeout_seconds": 0},
            "allowlist not a list": {"tools": {"x": good}, "environment_allowlist": "PATH"},
            "allowlist non-string element": {"tools": {"x": good}, "environment_allowlist": ["PATH", 1]},
            "invalid JSON": b"{\"tools\": ",
            "not UTF-8": b"\xff\xfe{}",
        }
        for label, cfg in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                fx = Fixture(Path(d))
                fx.write_config(cfg)
                for args in (("--tool", "x", "--dry-run"), ("--tool", "x"), ("--approve",)):
                    r = fx.run(*args)
                    self.assertEqual(r.returncode, EXIT_CONFIG, f"{label} {args}: {r.stdout}{r.stderr}")
                    self.assertIn("ERROR[config]", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertEqual(len(r.stderr.strip().splitlines()), 1, f"one-line error: {r.stderr}")
                    self.assertEqual(r.stdout, "")

    def test_missing_config_file_exit_5(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, EXIT_CONFIG, r.stderr)
            self.assertIn("ERROR[config]", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_optional_keys_and_utf8_bom_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            raw = b"\xef\xbb\xbf" + json.dumps({"tools": {"x": {"argv": [sys.executable, "x.py"]}}}).encode("utf-8")
            fx.write_config(raw)
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            plan = first_json(r.stdout)
            self.assertEqual(plan["timeout_seconds"], 3600)
            self.assertEqual(plan["config_sha256"], hashlib.sha256(raw).hexdigest(), "the hash binds the raw bytes")
            fx.write_config(config({"x": tool(["echo"])}, max_timeout_seconds=600))
            self.assertEqual(first_json(fx.run("--tool", "x", "--dry-run").stdout)["timeout_seconds"], 600)


class ApprovalTests(unittest.TestCase):
    """F3: execution needs an out-of-tree approval record bound to the exact config bytes."""

    def test_dry_run_spawns_nothing_and_reports_approval_state(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            marker = fx.tmp / "marker.txt"
            fx.write_config(config({"x": tool([sys.executable, fx.script("marker.py", MARKER_PY), str(marker),
                                                "--api-token=TOPSECRET-VALUE-1"])}))
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(marker.exists(), "dry-run must not spawn the tool")
            self.assertEqual(fx.run_dirs(), [], "dry-run writes no run record")
            plan = first_json(r.stdout)
            self.assertFalse(plan["approved"])
            self.assertTrue(plan["dry_run"])
            self.assertEqual(plan["argv"][-1], "--api-token=<redacted>")
            self.assertNotIn("TOPSECRET-VALUE-1", r.stdout + r.stderr)
            self.assertEqual(plan["resolved_executable"], str(Path(sys.executable)), "spawned path, links untouched")
            self.assertEqual(plan["executable_realpath"], str(Path(sys.executable).resolve()))
            self.assertEqual(plan["approval_record"], str(fx.approval_dir / f"{fx.sha()}.json"))
            self.assertIn("execution would be refused", r.stderr)
            fx.approve()
            r = fx.run("--tool", "x", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(first_json(r.stdout)["approved"])
            self.assertFalse(marker.exists())

    def test_unapproved_execution_refused_without_side_effect(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            marker = fx.tmp / "marker.txt"
            fx.write_config(config({"x": tool([sys.executable, fx.script("marker.py", MARKER_PY), str(marker)])}))
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, EXIT_UNAPPROVED, r.stderr)
            self.assertIn("ERROR[unapproved]", r.stderr)
            self.assertIn("--approve", r.stderr)
            self.assertIn(str(fx.config_path), r.stderr, "the hint names the exact config")
            self.assertIn(str(fx.approval_dir), r.stderr, "the hint carries the --approval-dir override")
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse(marker.exists(), "nothing may be spawned without an approval")
            self.assertEqual(fx.run_dirs(), [], "a refused execution leaves no run record")
            self.assertFalse(first_json(r.stdout)["approved"])

    def test_approved_run_exits_with_child_code_and_writes_run_record(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            emit = fx.script("emit.py", EMIT_PY)
            fx.write_config(config({"x": tool([sys.executable, emit, "3", "--password=TOPSECRET-VALUE-2"],
                                                timeout_seconds=30)}))
            record = fx.approve()
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertNotIn("TOPSECRET-VALUE-2", r.stdout + r.stderr)
            dirs = fx.run_dirs()
            self.assertEqual(len(dirs), 1, dirs)
            run_dir = dirs[0]
            self.assertIn(str(run_dir), r.stdout, "the record path is printed")
            result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            expected = {"schema_version", "run_id", "tool", "argv", "resolved_executable", "cwd", "config_path",
                        "config_sha256", "approval_record", "git_commit", "started_at", "ended_at",
                        "duration_seconds", "timeout_seconds", "return_code", "timed_out", "status", "python",
                        "platform", "environment"}
            self.assertLessEqual(expected, set(result), expected - set(result))
            self.assertEqual(result["run_id"], run_dir.name)
            self.assertEqual(result["tool"], "x")
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["return_code"], 3)
            self.assertEqual(result["exit_code"], 3)
            self.assertFalse(result["timed_out"])
            self.assertEqual(result["argv"][-1], "--password=<redacted>")
            self.assertEqual(result["config_sha256"], fx.sha())
            self.assertEqual(result["config_path"], str(fx.config_path))
            self.assertEqual(result["approval_record"], str(record))
            self.assertEqual(result["resolved_executable"], str(Path(sys.executable)))
            self.assertEqual(result["executable_realpath"], str(Path(sys.executable).resolve()))
            self.assertEqual(result["cwd"], str(fx.root))
            self.assertEqual(result["timeout_seconds"], 30)
            self.assertIsNone(result["git_commit"], "the throwaway project is not a git repository")
            self.assertIn("PATH", result["environment"])
            self.assertTrue(all(isinstance(n, str) and "=" not in n for n in result["environment"]), "names only")
            self.assertTrue(result["started_at"].endswith("Z") and result["ended_at"].endswith("Z"))
            self.assertIn(b"OUT-LINE", (run_dir / "stdout.log").read_bytes())
            self.assertIn(b"ERR-LINE", (run_dir / "stderr.log").read_bytes())
            self.assertNotIn(b"ERR-LINE", (run_dir / "stdout.log").read_bytes())
            fx.write_config(config({"x": tool([sys.executable, emit, "0"])}))
            fx.approve()
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, 0, r.stderr)
            new_dir = (set(fx.run_dirs()) - {run_dir}).pop()
            self.assertEqual(json.loads((new_dir / "result.json").read_text(encoding="utf-8"))["status"], "pass")

    def test_changed_config_bytes_invalidate_approval(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            marker = fx.tmp / "marker.txt"
            fx.write_config(config({"x": tool([sys.executable, fx.script("marker.py", MARKER_PY), str(marker)])}))
            fx.approve()
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(marker.exists())
            marker.unlink()
            fx.config_path.write_bytes(fx.config_path.read_bytes() + b"\n")  # one added byte: a different config
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, EXIT_UNAPPROVED, r.stderr)
            self.assertIn("no approval record", r.stderr)
            self.assertFalse(marker.exists())
            stale = fx.approval_dir / f"{fx.sha()}.json"  # right file name, but the content binds another hash
            stale.write_text(json.dumps({"schema_version": "1.0", "config_sha256": "0" * 64}), encoding="utf-8")
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, EXIT_UNAPPROVED, r.stderr)
            self.assertIn("does not bind", r.stderr)
            self.assertFalse(marker.exists())
            stale.write_text("{not json", encoding="utf-8")
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, EXIT_UNAPPROVED, r.stderr)
            self.assertFalse(marker.exists())

    def test_approve_without_tty_refused(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"x": tool([sys.executable, "x.py", "--token=TOPSECRET-VALUE-3"])},
                                   environment_allowlist=["PATH", "GITHUB_TOKEN"]))
            r = fx.run("--approve")  # stdin is /dev/null in Fixture.run, so it is not a terminal
            self.assertEqual(r.returncode, EXIT_APPROVAL_REFUSED, r.stderr)
            self.assertIn("ERROR[approval-refused]", r.stderr)
            self.assertIn("interactive", r.stderr)
            self.assertFalse(fx.approval_dir.exists(), "no record may be written")
            summary = first_json(r.stdout)
            self.assertEqual(summary["config_sha256"], fx.sha())
            self.assertEqual(summary["tools"]["x"]["argv"][-1], "--token=<redacted>")
            self.assertEqual(summary["environment_denied"], ["GITHUB_TOKEN"])
            self.assertNotIn("TOPSECRET-VALUE-3", r.stdout + r.stderr)
            fx.write_config(config({"ok": tool(["echo", "x"]), "bad": tool(["bash", "-c", "id"])}))
            r = fx.run("--approve")
            self.assertEqual(r.returncode, EXIT_ARGV, "an interpreter escape can never reach the approval prompt")
            fx.write_config(config({"ok": tool(["echo", "x"]), "bad": tool(["echo", "x"], cwd="../../")}))
            r = fx.run("--approve")
            self.assertEqual(r.returncode, EXIT_CWD, "an escaping cwd can never reach the approval prompt")
            self.assertFalse(fx.approval_dir.exists())

    def test_interactive_approve_writes_record_then_run_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            marker = fx.tmp / "marker.txt"
            fx.write_config(config({"x": tool([sys.executable, fx.script("marker.py", MARKER_PY), str(marker)])},
                                   environment_allowlist=["PATH", "GITHUB_TOKEN"]))
            mod = load_module()
            args = ["--config", str(fx.config_path), "--approve", "--approval-dir", str(fx.approval_dir)]
            tty = mock.Mock()
            tty.isatty.return_value = True
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, "stdin", tty), mock.patch("builtins.input", return_value="deadbeef"), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = mod.main(args)
            self.assertEqual(rc, EXIT_APPROVAL_REFUSED)
            self.assertIn("did not match", err.getvalue())
            self.assertFalse(fx.approval_dir.exists(), "a mismatch writes nothing")
            typed = fx.sha()[:8].upper()
            with mock.patch.object(sys, "stdin", tty), mock.patch("builtins.input", return_value=typed), \
                    contextlib.redirect_stdout(out):
                rc = mod.main(args)
            self.assertEqual(rc, 0)
            record_path = fx.approval_dir / f"{fx.sha()}.json"
            self.assertIn(str(record_path), out.getvalue())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            for key in ("schema_version", "config_sha256", "config_path", "approved_at", "approved_by", "tools"):
                self.assertIn(key, record)
            self.assertEqual(record["config_sha256"], fx.sha())
            self.assertEqual(record["config_path"], str(fx.config_path))
            self.assertEqual(record["tools"]["x"]["argv"][0], sys.executable)
            self.assertEqual(record["environment_denied"], ["GITHUB_TOKEN"])
            self.assertTrue(record["approved_at"].endswith("Z"))
            if not IS_WINDOWS:
                self.assertEqual(stat.S_IMODE(fx.approval_dir.stat().st_mode), 0o700)
            self.assertEqual([p.name for p in fx.approval_dir.iterdir()], [record_path.name], "no temp file left")
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(marker.exists())


class EnvironmentTests(unittest.TestCase):
    """F3 secret hard-deny and F17 PATH/essentials policy, observed from inside the child."""

    def _dump(self, fx: Fixture, allowlist: list, env_extra: dict):
        out = fx.tmp / "env.json"
        fx.write_config(config({"x": tool([sys.executable, fx.script("envdump.py", ENVDUMP_PY), str(out)])},
                               environment_allowlist=allowlist))
        fx.approve()
        r = fx.run("--tool", "x", env=env_extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, json.loads(out.read_text(encoding="utf-8"))

    def test_secret_named_variables_never_passed_even_when_allowlisted(self):
        secret_env = {"MY_API_TOKEN": "TOPSECRET-VALUE-4", "DB_PASSWORD": "TOPSECRET-VALUE-5",
                      "AWS_SECRET_ACCESS_KEY": "TOPSECRET-VALUE-6", "SESSION_COOKIE": "TOPSECRET-VALUE-7",
                      "SVC_CREDENTIAL": "TOPSECRET-VALUE-8", "OAUTH_THING": "TOPSECRET-VALUE-9"}
        plain_env = {"PLAIN_VAR": "plain-value", "NOT_ALLOWLISTED": "other-value"}
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            r, child = self._dump(fx, ["PLAIN_VAR", *secret_env], {**secret_env, **plain_env})
            self.assertEqual(child.get("PLAIN_VAR"), "plain-value", "allowlisted plain variable is passed")
            self.assertNotIn("NOT_ALLOWLISTED", child, "non-allowlisted variable is absent (default deny)")
            for name, value in secret_env.items():
                self.assertNotIn(name, child, f"{name} must never reach the child")
                self.assertNotIn(value, r.stdout + r.stderr, "values are never printed")
                self.assertIn(name, r.stderr, "denied names are reported")
            plan = first_json(r.stdout)
            self.assertEqual(plan["environment_denied"], sorted(secret_env))
            self.assertIn("PLAIN_VAR", plan["environment"])
            self.assertNotIn("NOT_ALLOWLISTED", plan["environment"])
            self.assertFalse(set(secret_env) & set(plan["environment"]))
            self.assertEqual(fx.result()["environment"], plan["environment"])
            self.assertEqual(fx.result()["environment_denied"], sorted(secret_env))

    def test_path_not_allowlisted_child_gets_defpath(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            r, child = self._dump(fx, [], {})
            self.assertEqual(child.get("PATH"), os.defpath)
            self.assertIn("PATH is not allowlisted", r.stderr)
            self.assertFalse(first_json(r.stdout)["path_from_parent"])

    def test_path_allowlisted_child_gets_parent_path(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            r, child = self._dump(fx, ["PATH"], {})
            self.assertEqual(child.get("PATH"), os.environ.get("PATH"))
            self.assertNotIn("PATH is not allowlisted", r.stderr)
            self.assertTrue(first_json(r.stdout)["path_from_parent"])

    @unittest.skipUnless(IS_WINDOWS, "Windows-only: OS-essential variables are passed only on win32")
    def test_windows_essential_variables_passed(self):  # pragma: no cover - Windows only
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            r, child = self._dump(fx, [], {})
            self.assertIn("SYSTEMROOT", child)
            for name in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
                if name in os.environ:
                    self.assertEqual(child.get(name), os.environ[name], name)

    @unittest.skipIf(IS_WINDOWS, "POSIX-only: uses a #! script as the tool executable")
    def test_bare_name_resolved_against_child_path(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            bindir = fx.tmp / "bin"
            bindir.mkdir()
            marker = fx.tmp / "marker.txt"
            script = bindir / "fake-tool"
            script.write_text('#!/bin/sh\necho ran > "$1"\n', encoding="utf-8")
            script.chmod(0o755)
            parent_path = f"{bindir}{os.pathsep}{os.environ.get('PATH', os.defpath)}"
            fx.write_config(config({"x": tool(["fake-tool", str(marker)])}, environment_allowlist=["PATH"]))
            fx.approve()
            r = fx.run("--tool", "x", env={"PATH": parent_path})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(marker.exists())
            self.assertEqual(first_json(r.stdout)["resolved_executable"], str(script.resolve()))
            self.assertEqual(fx.result()["resolved_executable"], str(script.resolve()))
            marker.unlink()
            # PATH not allowlisted: the child's PATH is os.defpath, where fake-tool does not exist -> exit 8
            fx.write_config(config({"x": tool(["fake-tool", str(marker)])}))
            fx.approve()
            r = fx.run("--tool", "x", env={"PATH": parent_path})
            self.assertEqual(r.returncode, EXIT_EXECUTABLE, r.stderr)
            self.assertIn("ERROR[executable]", r.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(len(fx.run_dirs()), 1, "nothing was attempted, so no second run record")

    def test_unresolvable_executable_exit_8_before_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            cases = {"bare name": ["no-such-tool-soc-dv-9f3a", "x"],
                     "missing absolute path": [str(fx.tmp / "missing-tool"), "x"],
                     "relative path outside the root": ["../helpers/anything", "x"],
                     "relative path missing inside the root": ["./tools/missing", "x"]}
            for label, argv in cases.items():
                with self.subTest(label):
                    fx.write_config(config({"x": tool(argv)}, environment_allowlist=["PATH"]))
                    fx.approve()
                    r = fx.run("--tool", "x")
                    self.assertEqual(r.returncode, EXIT_EXECUTABLE, f"{label}: {r.stdout}{r.stderr}")
                    self.assertIn("ERROR[executable]", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertEqual(fx.run_dirs(), [], "nothing was attempted, so no run record")
                    self.assertIsNone(first_json(r.stdout)["resolved_executable"])
                    r = fx.run("--tool", "x", "--dry-run")
                    self.assertEqual(r.returncode, 0, f"{label}: dry-run only reports the problem: {r.stderr}")
                    self.assertIn("notice: dry-run:", r.stderr)


class ProcessControlTests(unittest.TestCase):
    """F10 process-group termination on timeout and H6 signal-death exit codes."""

    @unittest.skipIf(IS_WINDOWS, "POSIX-only: observes the grandchild with kill(pid, 0) after an os.killpg")
    def test_timeout_kills_process_group_exit_124(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            pidfile = fx.tmp / "grandchild.pid"
            parent = fx.script("parent.py", PARENT_PY)
            grandchild = fx.script("grandchild.py", GRANDCHILD_PY)
            # 2 s rather than 1 s leaves slack for two interpreter start-ups on a loaded host before the kill
            fx.write_config(config({"x": tool([sys.executable, parent, grandchild, str(pidfile)],
                                                timeout_seconds=2)}))
            fx.approve()
            started = time.monotonic()
            r = fx.run("--tool", "x", timeout=60)
            elapsed = time.monotonic() - started
            self.assertEqual(r.returncode, EXIT_TIMEOUT, r.stderr)
            self.assertLess(elapsed, 45, "the group must be terminated promptly after the timeout")
            self.assertTrue(pidfile.exists(), "the grandchild never started, so the group kill cannot be judged")
            gpid = int(pidfile.read_text(encoding="utf-8"))
            try:
                deadline = time.monotonic() + 10
                while not pid_gone(gpid) and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(pid_gone(gpid), f"grandchild {gpid} survived the timeout of its process group")
            finally:
                if not pid_gone(gpid):
                    os.kill(gpid, signal.SIGKILL)
            result = fx.result()
            self.assertEqual(result["status"], "timeout")
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["exit_code"], EXIT_TIMEOUT)
            self.assertEqual(result["timeout_seconds"], 2)
            self.assertIn("run result: status=timeout", r.stdout)

    @unittest.skipIf(IS_WINDOWS, "POSIX-only: signal deaths do not exist on Windows")
    def test_signal_death_maps_to_128_plus_n(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"x": tool([sys.executable, fx.script("selfkill.py", SELFKILL_PY)])}))
            fx.approve()
            r = fx.run("--tool", "x")
            self.assertEqual(r.returncode, 128 + int(signal.SIGTERM), r.stderr)
            result = fx.result()
            self.assertEqual(result["return_code"], -int(signal.SIGTERM))
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["exit_code"], 128 + int(signal.SIGTERM))


class HelperTests(unittest.TestCase):
    """In-process checks of the record helpers and the usage contract."""

    def test_git_commit_read_from_dot_git_without_invoking_git(self):
        mod = load_module()
        sha_a, sha_b = "a" * 40, "b" * 40
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d).resolve()
            repo = tmp / "repo"
            (repo / ".git" / "refs" / "heads").mkdir(parents=True)
            (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (repo / ".git" / "refs" / "heads" / "main").write_text(sha_a + "\n", encoding="utf-8")
            self.assertEqual(mod.git_commit(repo), sha_a)
            (repo / ".git" / "refs" / "heads" / "main").unlink()
            (repo / ".git" / "packed-refs").write_text(
                f"# pack-refs with: peeled fully-peeled sorted\n{sha_b} refs/heads/main\n^{'c' * 40}\n",
                encoding="utf-8")
            self.assertEqual(mod.git_commit(repo), sha_b)
            worktree = tmp / "wt"
            worktree.mkdir()
            wt_git = repo / ".git" / "worktrees" / "wt"
            wt_git.mkdir(parents=True)
            (worktree / ".git").write_text(f"gitdir: {wt_git}\n", encoding="utf-8")
            (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
            (wt_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            self.assertEqual(mod.git_commit(worktree), sha_b)
            (repo / ".git" / "HEAD").write_text(sha_a + "\n", encoding="utf-8")  # detached HEAD
            self.assertEqual(mod.git_commit(repo), sha_a)
            self.assertIsNone(mod.git_commit(tmp / "not-a-repo"))

    def test_redaction_covers_name_value_forms_only(self):
        mod = load_module()
        cases = {"--api-token=abc": "--api-token=<redacted>", "--password=hunter2": "--password=<redacted>",
                 "passwd=x": "passwd=<redacted>", "API_KEY=zz": "API_KEY=<redacted>",
                 "Secret: s3": "Secret: <redacted>", "cookie=a=b": "cookie=<redacted>",
                 "credential=c": "credential=<redacted>", "https://h/?token=t&x=1": "https://h/?token=<redacted>",
                 "plain": "plain", "-Wall": "-Wall", "files.f": "files.f", "--tokenizer": "--tokenizer"}
        self.assertEqual(mod.redact(list(cases)), list(cases.values()))

    def test_help_and_usage_errors(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, str(RUN_TOOL), "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        for flag in ("--config", "--tool", "--dry-run", "--approve", "--approval-dir"):
            self.assertIn(flag, r.stdout)
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.write_config(config({"x": tool(["echo"])}))
            self.assertEqual(fx.run().returncode, 2, "--tool is required unless --approve is given")
            self.assertEqual(fx.run("--approve", "--tool", "x").returncode, 2, "--approve excludes --tool")
            self.assertEqual(fx.run("--approve", "--dry-run").returncode, 2, "--approve excludes --dry-run")


if __name__ == "__main__":
    unittest.main()
