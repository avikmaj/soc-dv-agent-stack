"""Regression test for audit finding F12: the repository's .gitignore ignores DV artifacts, secret material and
stack-local state without hiding source, evidence or the canonical templates.

Run: python3 -m unittest tests.test_gitignore -v

The repository's .gitignore is copied into a fresh `git init` repository inside a temporary directory and every
verdict comes from `git check-ignore --no-index` there, so it is purely pattern-based: no path in the tables has
to exist, the index plays no part, and system and global git configuration are disabled so a developer's own
excludes cannot influence the result. The real repository is only read (its .gitignore and its `git ls-files`
list); nothing in it is written. The pattern checks are skipped with a reason when `git` is not on PATH; the
byte-level checks never need git.

Tables (module level; one row per pattern or per documented trade-off):
  EXISTING_PATTERNS   the pre-F12 entries that must survive verbatim and in their original relative order
  FORBIDDEN_PATTERNS  broad patterns that would hide source, evidence or the canonical templates
  MUST_IGNORE         one representative path per pattern, nested where the artifact normally is
  MUST_NOT_IGNORE     source, evidence, templates and look-alike names that stay visible (plus every tracked file)
"""
import codecs
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITIGNORE = ROOT / ".gitignore"
MAX_LINE = 120

# The 19 entries that existed before F12, in file order (the order carries the negation `!.env.example`).
EXISTING_PATTERNS = (
    "__pycache__/", "*.py[cod]", ".pytest_cache/", ".venv/", "venv/",
    ".env", ".env.*", "!.env.example",
    "**/.soc-dv/runs/", "**/.soc-dv/cache/",  # widened from the root-only forms to match nested projects too
    "*.log",
    "*.vcd", "*.fst", "*.wlf", "*.fsdb",
    "*.ucdb", "*.vdb/",
    "*.key", "*.pem",
)

# Compared after stripping a leading `/` or `**/` and a trailing `/`; negations (`!...`) are never offenders.
FORBIDDEN_PATTERNS = frozenset({
    "*", "**", "*.json", "*.md", "*.py", "*.sv", "*.svh", "*.v", "*.vh", "*.txt", "*.yml", "*.yaml", "*.toml",
    "templates", "schemas", "skills", "docs", "tests", "scripts", ".github", ".claude", ".agents", "orgs",
    "LICENSE", "VERSION", "CHANGELOG.md", "README.md", "pyproject.toml", ".gitattributes", ".gitignore",
    "templates/project-config.example.json", "templates/verification-plan.example.json",
})

# (path, pattern expected to catch it). The pattern is documentation for the failure message only: git reports
# the last matching pattern, so a path caught by two patterns is not pinned to one of them.
MUST_IGNORE = (
    # Python bytecode, virtual environments, caches, build output
    ("pkg/__pycache__/mod.cpython-312.pyc", "__pycache__/"),
    ("pkg/mod.pyc", "*.py[cod]"),
    (".pytest_cache/v/cache/nodeids", ".pytest_cache/"),
    (".venv/bin/python", ".venv/"),
    ("venv/lib/site.py", "venv/"),
    ("dist/x.whl", "dist/"),
    ("build/lib/x.py", "build/"),
    ("pkg.egg-info/PKG-INFO", "*.egg-info/"),
    (".coverage", ".coverage"),
    ("htmlcov/index.html", "htmlcov/"),
    (".mypy_cache/3.12/x.json", ".mypy_cache/"),
    (".ruff_cache/x", ".ruff_cache/"),
    (".tox/py312/x", ".tox/"),
    # Environment files
    (".env", ".env"),
    (".env.local", ".env.*"),
    # Stack-local state at the project root and in a project nested below this file
    (".soc-dv/runs/run-1/result.json", "**/.soc-dv/runs/"),
    (".soc-dv/cache/x", "**/.soc-dv/cache/"),
    ("sub/project/.soc-dv/runs/run-1/result.json", "**/.soc-dv/runs/"),
    ("sub/project/.soc-dv/cache/x", "**/.soc-dv/cache/"),
    (".soc-dv/config.json", "**/.soc-dv/config.json"),
    (".soc-dv/install-manifest.json", "**/.soc-dv/install-manifest.json"),
    (".soc-dv/journal/20260101T000000Z-deadbeef.jsonl", "**/.soc-dv/journal/"),
    (".soc-dv/backups/id/CLAUDE.md", "**/.soc-dv/backups/"),
    ("sub/project/.soc-dv/config.json", "**/.soc-dv/config.json"),
    ("sub/project/.soc-dv/install-manifest.json", "**/.soc-dv/install-manifest.json"),
    ("sub/project/.soc-dv/journal/20260101T000000Z-deadbeef.jsonl", "**/.soc-dv/journal/"),
    ("sub/project/.soc-dv/backups/id/AGENTS.md", "**/.soc-dv/backups/"),
    # Simulator build output and logs
    ("sim/run.log", "*.log"),
    ("sim/simv", "simv"),
    ("sim/simv.old", "simv.*"),  # any other simv-prefixed leftover beside the binary
    ("sim/simv.daidir/foo", "*.daidir/"),
    ("sim/mysim.daidir/foo", "*.daidir/"),
    ("sim/csrc/x.o", "csrc/"),
    ("xcelium.d/run.d/x", "xcelium.d/"),
    ("INCA_libs/worklib/x", "INCA_libs/"),
    ("sim/work/_info", "work/"),
    ("sim/transcript", "transcript"),
    # Waveforms and dumps
    ("waves.vcd", "*.vcd"),
    ("waves.fst", "*.fst"),
    ("sim/vsim.wlf", "*.wlf"),
    ("waves.fsdb", "*.fsdb"),
    ("waves.vpd", "*.vpd"),
    ("dump.shm/x", "*.shm/"),
    ("sim/waves.trn", "*.trn"),
    ("sim/waves.dsn", "*.dsn"),
    # Coverage databases and debug-tool output
    ("cov/merged.ucdb", "*.ucdb"),
    ("cov/merged.vdb/x", "*.vdb/"),
    ("out/cov_work/scope", "cov_work/"),
    ("urgReport/dashboard.html", "urgReport/"),
    ("verdiLog/x", "verdiLog/"),
    ("novas.conf", "novas*"),
    ("sim/novas_dump.log", "novas*"),
    ("DVEfiles/x", "DVEfiles/"),
    # Credentials and secret material
    ("server.key", "*.key"),
    ("cert.pem", "*.pem"),
    ("client.p12", "*.p12"),
    ("client.pfx", "*.pfx"),
    ("id_rsa", "id_rsa"),
    ("id_rsa.pub", "id_rsa.*"),  # decision: the public half beside a private key is ignored as well
    (".ssh/id_ed25519", "id_ed25519"),
    (".ssh/id_ed25519.pub", "id_ed25519.*"),
    (".netrc", ".netrc"),
    (".pypirc", ".pypirc"),
    ("credentials.json", "credentials*.json"),
    ("credentials-prod.json", "credentials*.json"),
    ("secrets.token", "*.token"),
    ("deploy.secret", "*.secret"),
)

# (path, why it must stay visible). Every file tracked in this repository is checked as well.
MUST_NOT_IGNORE = (
    ("templates/project-config.example.json", "canonical template; only .soc-dv/config.json is local state"),
    ("templates/verification-plan.example.json", "canonical template"),
    ("schemas/waiver.schema.json", "schema"),
    (".env.example", "re-included by !.env.example"),
    ("docs/scripts.md", "documentation"),
    ("tests/test_stack.py", "test source"),
    ("skills/formal-sva/SKILL.md", "canonical skill"),
    ("modelsim.ini", "real Questa configuration that users may commit"),
    ("README.md", "documentation"),
    ("pyproject.toml", "project metadata"),
    (".gitattributes", "byte-stability policy"),
    ("VERSION", "single-source version"),
    ("sim/Makefile", "build recipe, not build output"),
    ("rtl/top.sv", "RTL source; no .sv is tracked here, so only this row would notice a *.sv pattern"),
    ("tb/env.sv", "testbench source"),
    ("tb/work_items.sv", "work/ matches only a directory named exactly work"),
    ("workbench/notes.md", "work/ must not catch workbench/"),
    ("builder.py", "build/ must not catch builder.py"),
    ("src/build_tools/x.py", "build/ must not catch build_tools/"),
    ("docs/distribution.md", "dist/ must not catch distribution.md"),
    ("sim/simverify.py", "simv and simv.* must not catch simverify.py"),
    ("transcripts/2026-01-01.md", "transcript matches only the exact name"),
    ("docs/transcript.md", "transcript has no wildcard"),
    ("config.json", "only .soc-dv/config.json is stack-local state"),
    ("install-manifest.json", "only .soc-dv/install-manifest.json is stack-local state"),
    ("sub/project/config.json", "a project's own config.json outside .soc-dv/ is not stack state"),
    ("coverage.xml", "deliberately not ignored: not DV-specific and sometimes committed as a baseline"),
    ("docs/coverage.md", "coverage documentation"),
    ("docs/token-format.md", "*.token is an extension, not a substring"),
    ("docs/secret-handling.md", "*.secret is an extension, not a substring"),
    ("keys.md", "*.key is an extension, not a substring"),
)

# Environment variables that would redirect git at another repository or inject configuration.
_GIT_REDIRECTS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
)


def _pattern_lines() -> list[str]:
    """Non-blank, non-comment lines of the repository's .gitignore, in order."""
    lines = GITIGNORE.read_bytes().decode("utf-8").split("\n")
    return [line for line in lines if line and not line.startswith("#")]


def _hermetic_git_env(home: Path) -> dict[str, str]:
    """An environment in which git sees no system, global or inherited repository configuration."""
    env = {k: v for k, v in os.environ.items()
           if k not in _GIT_REDIRECTS and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update({
        "HOME": str(home), "USERPROFILE": str(home), "XDG_CONFIG_HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(home / "gitconfig"),
        "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
    })
    return env


class GitignoreTextTests(unittest.TestCase):
    """Byte hygiene and pattern-list invariants; needs no git."""

    def test_bytes_are_utf8_lf_with_one_trailing_newline(self):
        data = GITIGNORE.read_bytes()
        self.assertFalse(data.startswith(codecs.BOM_UTF8), ".gitignore starts with a UTF-8 BOM")
        text = data.decode("utf-8")  # strict: raises on invalid UTF-8
        self.assertNotIn("\r", text, ".gitignore contains a CR byte; it must be LF only")
        self.assertTrue(data.endswith(b"\n") and not data.endswith(b"\n\n"), "exactly one trailing newline")
        for n, line in enumerate(text.split("\n")[:-1], 1):
            self.assertLessEqual(len(line), MAX_LINE, f".gitignore line {n} is longer than {MAX_LINE} characters")
            self.assertEqual(line, line.rstrip(), f".gitignore line {n} has trailing whitespace")

    def test_patterns_are_unique(self):
        patterns = _pattern_lines()
        duplicates = sorted({p for p in patterns if patterns.count(p) > 1})
        self.assertEqual(duplicates, [], f"duplicate patterns: {duplicates}")

    def test_existing_patterns_survive_verbatim_in_order(self):
        patterns = _pattern_lines()
        missing = [p for p in EXISTING_PATTERNS if p not in patterns]
        self.assertEqual(missing, [], f"pre-F12 patterns missing or altered: {missing}")
        positions = [patterns.index(p) for p in EXISTING_PATTERNS]
        self.assertEqual(positions, sorted(positions), "relative order of the pre-F12 patterns changed")

    def test_no_broad_pattern(self):
        offenders = []
        for pattern in _pattern_lines():
            if pattern.startswith("!"):
                continue
            norm = pattern[1:] if pattern.startswith("/") else pattern
            if norm.startswith("**/"):
                norm = norm[3:]
            if norm.rstrip("/") in FORBIDDEN_PATTERNS:
                offenders.append(pattern)
        self.assertEqual(offenders, [], f"patterns that would hide source, evidence or templates: {offenders}")

    def test_every_pattern_has_a_representative_row(self):
        patterns = [p for p in _pattern_lines() if not p.startswith("!")]
        hints = {hint for _, hint in MUST_IGNORE}
        self.assertEqual([p for p in patterns if p not in hints], [], "patterns without a MUST_IGNORE row")
        self.assertEqual(sorted(hints - set(patterns)), [], "MUST_IGNORE hints that are not .gitignore patterns")


class GitignoreMatchTests(unittest.TestCase):
    """Pattern verdicts from `git check-ignore --no-index` in a temporary repository holding a copy of .gitignore."""

    @classmethod
    def setUpClass(cls):
        cls.git = shutil.which("git")
        if not cls.git:
            raise unittest.SkipTest("git is not on PATH; the pattern verdicts need `git check-ignore`")
        cls._tmp = tempfile.TemporaryDirectory(prefix="f12-gitignore-", ignore_cleanup_errors=True)
        base = Path(cls._tmp.name)
        home = base / "home"
        home.mkdir()
        (home / "gitconfig").write_bytes(b"")
        cls.repo = base / "repo"
        cls.repo.mkdir()
        cls.env = _hermetic_git_env(home)
        result = subprocess.run([cls.git, "init", "-q", "."], cwd=cls.repo, env=cls.env, capture_output=True)
        if result.returncode:
            cls._tmp.cleanup()
            raise RuntimeError(f"git init failed in {cls.repo}: {result.stderr.decode(errors='replace').strip()}")
        shutil.copyfile(GITIGNORE, cls.repo / ".gitignore")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _is_ignored(self, path: str) -> bool:
        """`git check-ignore -q --no-index -- <path>`: exit 0 means ignored, 1 means not ignored."""
        result = subprocess.run([self.git, "check-ignore", "-q", "--no-index", "--", path],
                                cwd=self.repo, env=self.env, capture_output=True)
        self.assertIn(result.returncode, (0, 1),
                      f"git check-ignore failed for {path!r}: {result.stderr.decode(errors='replace').strip()}")
        return result.returncode == 0

    def _verdicts(self, paths: list[str]) -> dict[str, str]:
        """One `git check-ignore --stdin -z -n -v --no-index` call: {path: 'source:line:pattern' or ''}.

        With -v git also reports a path whose last match is a negation (`!pattern`); that path is re-included,
        not ignored, so it receives the empty verdict like a path that matches nothing.
        """
        data = b"".join(p.encode("utf-8") + b"\0" for p in paths)
        result = subprocess.run([self.git, "check-ignore", "--no-index", "--stdin", "-z", "-n", "-v"],
                                cwd=self.repo, env=self.env, input=data, capture_output=True)
        self.assertIn(result.returncode, (0, 1),
                      f"git check-ignore --stdin failed: {result.stderr.decode(errors='replace').strip()}")
        fields = result.stdout.decode("utf-8").split("\0")
        self.assertEqual(fields.pop(), "", "check-ignore -z output must end with NUL")
        self.assertEqual(len(fields) % 4, 0, "check-ignore -z output is not made of 4-field records")
        verdicts = {}
        for i in range(0, len(fields), 4):
            source, line, pattern, path = fields[i:i + 4]
            ignored = bool(pattern) and not pattern.startswith("!")
            verdicts[path] = f"{source}:{line}:{pattern}" if ignored else ""
        self.assertEqual(sorted(verdicts), sorted(set(paths)), "every path must receive exactly one verdict")
        return verdicts

    def test_required_paths_are_ignored(self):
        for path, pattern in MUST_IGNORE:
            with self.subTest(path=path, pattern=pattern):
                self.assertTrue(self._is_ignored(path), f"{path!r} is not ignored; expected {pattern!r} to match")

    def test_representative_paths_are_not_ignored(self):
        verdicts = self._verdicts([path for path, _ in MUST_NOT_IGNORE])
        for path, why in MUST_NOT_IGNORE:
            with self.subTest(path=path):
                self.assertEqual(verdicts[path], "", f"{path!r} is ignored by {verdicts[path]}; {why}")

    def test_tracked_files_are_not_ignored(self):
        # The real repository is read with the inherited environment so its own safe.directory settings apply.
        result = subprocess.run([self.git, "-C", str(ROOT), "ls-files", "-z"], capture_output=True)
        if result.returncode:
            self.skipTest(f"git ls-files is unavailable for {ROOT}: {result.stderr.decode(errors='replace').strip()}")
        tracked = [p for p in result.stdout.decode("utf-8").split("\0") if p]
        self.assertIn(".gitignore", tracked, "tracked-file list looks wrong")
        self.assertIn("README.md", tracked, "tracked-file list looks wrong")
        hidden = {path: by for path, by in self._verdicts(tracked).items() if by}
        self.assertEqual(hidden, {}, f"tracked files matched by an ignore pattern: {hidden}")


if __name__ == "__main__":
    unittest.main()
