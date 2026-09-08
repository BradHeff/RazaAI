"""Coding evaluation tasks."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Task:
    id: str
    language: str
    request: str
    setup: Callable[[Path], None]
    check: Callable[[Path], tuple[bool, str]]
    tags: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # Binaries that must exist


def _w(ws: Path, rel: str, text: str):
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_init(ws: Path):
    subprocess.run(["git", "init", "-q"], cwd=ws, check=False)
    subprocess.run(["git", "-c", "user.name=e", "-c", "user.email=e@e", "add", "-A"], cwd=ws, check=False)
    subprocess.run(["git", "-c", "user.name=e", "-c", "user.email=e@e", "commit", "-q", "-m", "fixture"], cwd=ws, check=False)


def _py_run(ws: Path, *args, timeout=60):
    return subprocess.run(["python3", *args], cwd=ws, capture_output=True, text=True, timeout=timeout,
                          env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"})


def _defines(ws: Path, rel: str, name: str) -> bool:
    try:
        tree = ast.parse((ws / rel).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name for n in ast.walk(tree))


def _unchanged(ws: Path, rel: str, original: str) -> bool:
    try:
        return (ws / rel).read_text(encoding="utf-8") == original
    except OSError:
        return False


# Python tasks


CALC = "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"
CALC_TEST = ("import unittest\n\nfrom calc import add, multiply\n\n\nclass TestCalc(unittest.TestCase):\n"
             "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n"
             "    def test_multiply(self):\n        self.assertEqual(multiply(2, 3), 6)\n\n\n"
             "if __name__ == '__main__':\n    unittest.main()\n")


def t01_setup(ws):
    _w(ws, "calc.py", CALC); _w(ws, "test_calc.py", CALC_TEST); _git_init(ws)


def t01_check(ws):
    if not _defines(ws, "calc.py", "sub"):
        return False, "calc.py does not define sub()"
    tests = (ws / "test_calc.py").read_text(encoding="utf-8")
    if "sub" not in tests or "def test_" not in tests or tests.count("def test_") < 3:
        return False, "test_calc.py has no new test for sub"
    run = _py_run(ws, "-m", "unittest", "-q")
    return run.returncode == 0, (run.stderr or run.stdout)[-300:]


def t02_setup(ws):
    filler = "".join(f"def helper_{i}(x):\n    return x + {i}\n\n\n" for i in range(120))
    _w(ws, "pkg/__init__.py", "")
    _w(ws, "pkg/engine.py", "import json\n\n\n" + filler +
       "def parse_invoice(raw):\n    return json.loads(raw)\n")
    _w(ws, "pkg/api.py", "from pkg.engine import parse_invoice\n\n\ndef handle(body):\n    return parse_invoice(body)\n")
    _w(ws, "tests/__init__.py", "")
    _w(ws, "tests/test_engine.py", "import unittest\n\nfrom pkg.engine import parse_invoice\n\n\nclass T(unittest.TestCase):\n"
       "    def test_parse(self):\n        self.assertEqual(parse_invoice('{\"a\": 1}'), {'a': 1})\n")
    for i in range(25):
        _w(ws, f"misc/mod_{i}.py", f"VALUE = {i}\n")
    _git_init(ws)


def t02_check(ws):
    src = (ws / "pkg/engine.py").read_text(encoding="utf-8")
    if "def helper_119" not in src or "def parse_invoice" not in src:
        return False, "engine.py lost content"
    probe = ("import sys; sys.path.insert(0, '.')\nfrom pkg.engine import parse_invoice\n"
             "try:\n    parse_invoice('')\n    print('NO-RAISE')\nexcept ValueError:\n    print('OK')\n")
    _w(ws, "_probe.py", probe)
    run = _py_run(ws, "_probe.py")
    if "OK" not in run.stdout:
        return False, f"parse_invoice('') did not raise ValueError: {(run.stderr or run.stdout)[-200:]}"
    tests = _py_run(ws, "-m", "unittest", "-q")
    return tests.returncode == 0, (tests.stderr or tests.stdout)[-300:]


def t03_setup(ws):
    _w(ws, "shapes.py", "import math\n\n\ndef circle_area(r):\n    return math.pi * r * r\n\n\ndef square_area(s):\n    return s * s\n")
    _w(ws, "report.py", "from shapes import circle_area, square_area\n\n\ndef summary(r, s):\n    return f'{circle_area(r):.2f} {square_area(s):.2f}'\n")
    _w(ws, "test_shapes.py", "import unittest\n\nfrom shapes import circle_area, square_area\nfrom report import summary\n\n\nclass T(unittest.TestCase):\n"
       "    def test_circle(self):\n        self.assertAlmostEqual(circle_area(1), 3.14159, places=4)\n\n"
       "    def test_square(self):\n        self.assertEqual(square_area(3), 9)\n\n"
       "    def test_summary(self):\n        self.assertEqual(summary(1, 2), '3.14 4.00')\n")
    _git_init(ws)


def t03_check(ws):
    for rel, name in (("shapes.py", "area_of_circle"), ("shapes.py", "area_of_square")):
        if not _defines(ws, rel, name):
            return False, f"{rel} does not define {name}"
    if _defines(ws, "shapes.py", "circle_area") or _defines(ws, "shapes.py", "square_area"):
        return False, "old names still defined (rename, not alias)"
    for rel in ("report.py", "test_shapes.py"):
        if "circle_area" in (ws / rel).read_text(encoding="utf-8"):
            return False, f"{rel} still references circle_area"
    run = _py_run(ws, "-m", "unittest", "-q")
    return run.returncode == 0, (run.stderr or run.stdout)[-300:]


def t04_setup(ws):
    _w(ws, "slugify.py", "import re\n\n\ndef slugify(text):\n    text = text.lower()\n    return re.sub(r'[^a-z0-9]+', '-', text)\n")
    _w(ws, "test_slugify.py", "import unittest\n\nfrom slugify import slugify\n\n\nclass T(unittest.TestCase):\n"
       "    def test_basic(self):\n        self.assertEqual(slugify('Hello World'), 'hello-world')\n\n"
       "    def test_trim(self):\n        self.assertEqual(slugify('  Hello, World!  '), 'hello-world')\n")
    _git_init(ws)


def t04_check(ws):
    run = _py_run(ws, "-m", "unittest", "-q")
    tests = (ws / "test_slugify.py").read_text(encoding="utf-8")
    if "'hello-world'" not in tests or tests.count("assertEqual") < 2:
        return False, "the test was weakened instead of the code being fixed"
    return run.returncode == 0, (run.stderr or run.stdout)[-300:]


def t05_setup(ws):
    _w(ws, "cli.py", "import argparse\n\n\ndef build_parser():\n    parser = argparse.ArgumentParser(prog='tool')\n"
       "    parser.add_argument('path')\n    return parser\n\n\ndef main(argv=None):\n    args = build_parser().parse_args(argv)\n"
       "    print(args.path)\n    return 0\n\n\nif __name__ == '__main__':\n    raise SystemExit(main())\n")
    _w(ws, "test_cli.py", "import unittest\n\nfrom cli import build_parser\n\n\nclass T(unittest.TestCase):\n"
       "    def test_path(self):\n        self.assertEqual(build_parser().parse_args(['x']).path, 'x')\n")
    _git_init(ws)


def t05_check(ws):
    probe = "from cli import build_parser\nprint(build_parser().parse_args(['x', '--verbose']).verbose)\nprint(build_parser().parse_args(['x']).verbose)\n"
    _w(ws, "_probe.py", probe)
    run = _py_run(ws, "_probe.py")
    if run.stdout.split() != ["True", "False"]:
        return False, f"--verbose flag not a store_true default False: {(run.stderr or run.stdout)[-200:]}"
    tests = _py_run(ws, "-m", "unittest", "-q")
    return tests.returncode == 0, (tests.stderr or tests.stdout)[-300:]


README = "# tool\n\nA small tool.\n"


def t06_setup(ws):
    _w(ws, "README.md", README); _w(ws, "tool.py", "def run():\n    return 1\n"); _git_init(ws)


def t06_check(ws):
    readme = (ws / "README.md").read_text(encoding="utf-8")
    if "## Installation" not in readme and "## Install" not in readme:
        return False, "README has no Installation section"
    if "pip install" not in readme:
        return False, "Installation section has no pip install command"
    if not _unchanged(ws, "tool.py", "def run():\n    return 1\n"):
        return False, "tool.py was modified by a docs-only request"
    return True, "ok"


def t07_setup(ws):
    _w(ws, "store.py", "class Store:\n    def __init__(self):\n        self._items = {}\n\n    def put(self, key, value):\n        self._items[key] = value\n\n    def get(self, key):\n        return self._items[key]\n")
    _w(ws, "test_store.py", "import unittest\n\nfrom store import Store\n\n\nclass T(unittest.TestCase):\n    def test_roundtrip(self):\n        s = Store(); s.put('a', 1)\n        self.assertEqual(s.get('a'), 1)\n")
    _w(ws, "unrelated.py", "X = 1\n")
    _git_init(ws)


def t07_check(ws):
    if not _unchanged(ws, "unrelated.py", "X = 1\n"):
        return False, "unrelated.py was touched"
    probe = "from store import Store\ns = Store(); s.put('a', 1)\nprint(s.get('missing', 'dflt'))\nprint(s.get('a'))\n"
    _w(ws, "_probe.py", probe)
    run = _py_run(ws, "_probe.py")
    if run.stdout.split() != ["dflt", "1"]:
        return False, f"get() has no working default: {(run.stderr or run.stdout)[-200:]}"
    tests = _py_run(ws, "-m", "unittest", "-q")
    return tests.returncode == 0, (tests.stderr or tests.stdout)[-300:]


def t08_setup(ws):
    _w(ws, "app/__init__.py", "")
    _w(ws, "app/models.py", "from dataclasses import dataclass\n\n\n@dataclass\nclass User:\n    name: str\n    email: str\n")
    _w(ws, "app/service.py", "from app.models import User\n\n\ndef register(name, email):\n    return User(name=name, email=email)\n")
    _w(ws, "tests/__init__.py", "")
    _w(ws, "tests/test_service.py", "import unittest\n\nfrom app.service import register\n\n\nclass T(unittest.TestCase):\n    def test_register(self):\n        self.assertEqual(register('a', 'a@x').email, 'a@x')\n")
    _git_init(ws)


def t08_check(ws):
    probe = ("import sys; sys.path.insert(0, '.')\nfrom app.service import register\n"
             "try:\n    register('a', 'not-an-email')\n    print('NO-RAISE')\nexcept ValueError:\n    print('OK')\n"
             "print(register('b', 'b@x.io').email)\n")
    _w(ws, "_probe.py", probe)
    run = _py_run(ws, "_probe.py")
    if run.stdout.split() != ["OK", "b@x.io"]:
        return False, f"email validation missing or wrong: {(run.stderr or run.stdout)[-200:]}"
    tests_text = (ws / "tests/test_service.py").read_text(encoding="utf-8")
    if "ValueError" not in tests_text and "assertRaises" not in tests_text:
        return False, "no test covers the invalid-email case"
    tests = _py_run(ws, "-m", "unittest", "-q")
    return tests.returncode == 0, (tests.stderr or tests.stdout)[-300:]


# Node task (only when node is installed)


def t09_setup(ws):
    _w(ws, "package.json", json.dumps({"name": "demo", "version": "1.0.0", "type": "module",
                                       "scripts": {"test": "node --test"}}, indent=2) + "\n")
    _w(ws, "math.js", "export function add(a, b) {\n  return a + b;\n}\n")
    _w(ws, "math.test.js", "import test from 'node:test';\nimport assert from 'node:assert';\nimport { add } from './math.js';\n\n"
       "test('add', () => {\n  assert.strictEqual(add(2, 3), 5);\n});\n")
    _git_init(ws)


def t09_check(ws):
    src = (ws / "math.js").read_text(encoding="utf-8")
    if not re.search(r"export\s+function\s+clamp\s*\(", src):
        return False, "math.js does not export clamp()"
    tests = (ws / "math.test.js").read_text(encoding="utf-8")
    if "clamp" not in tests:
        return False, "no test for clamp"
    run = subprocess.run(["node", "--test"], cwd=ws, capture_output=True, text=True, timeout=60)
    return run.returncode == 0, (run.stderr or run.stdout)[-300:]


TASKS: list[Task] = [
    Task("py.add_with_test", "python", "add a sub function to calc.py and a unittest for it", t01_setup, t01_check, ["add", "test"]),
    Task("py.edit_buried_function", "python", "make parse_invoice raise ValueError when raw is empty, and keep the existing tests passing", t02_setup, t02_check, ["edit", "exploration"]),
    Task("py.rename_across_files", "python", "rename circle_area to area_of_circle and square_area to area_of_square everywhere, including report.py and the tests", t03_setup, t03_check, ["refactor", "multi-file"]),
    Task("py.fix_failing_test", "python", "the test suite fails; fix the code in slugify.py so test_trim passes without changing the tests", t04_setup, t04_check, ["fix"]),
    Task("py.add_cli_flag", "python", "add a --verbose boolean flag to the argparse parser in cli.py (store_true, default False) and a test for it", t05_setup, t05_check, ["feature", "test"]),
    Task("docs.readme_install", "docs", "add an Installation section to README.md with a pip install command; do not change any code", t06_setup, t06_check, ["docs", "trap"]),
    Task("py.default_arg_trap", "python", "give Store.get in store.py an optional default parameter returned when the key is missing; leave unrelated.py alone", t07_setup, t07_check, ["edit", "trap"]),
    Task("py.validate_and_test", "python", "make register in app/service.py raise ValueError when the email has no @, and add a test for that case", t08_setup, t08_check, ["edit", "test", "package"]),
    Task("js.add_with_test", "javascript", "add an exported clamp(value, min, max) function to math.js and a test for it in math.test.js", t09_setup, t09_check, ["add", "test", "node"], requires=["node"]),
]


def available_tasks(include_requires=True):
    out = []
    for task in TASKS:
        if include_requires and any(shutil.which(b) is None for b in task.requires):
            continue
        out.append(task)
    return out
