"""Reference planner clients for the coding eval."""

import json

_TEST_SUB = "\n    def test_sub(self):\n        self.assertEqual(sub(5, 3), 2)\n"


def _plan(files, summary):
    return {"message": {"content": json.dumps({"files": files, "summary": summary})}}


class GoldenClient:
    last_usage = {"prompt_tokens": 1000, "output_tokens": 200}

    def chat(self, messages, tools=None):
        req = messages[-1]["content"].split("\n", 1)[0].replace("REQUEST: ", "").casefold()
        if "sub function" in req:
            return _plan([
                {"path": "calc.py", "mode": "patch", "old_text": "    return a * b\n", "new_text": "    return a * b\n\n\ndef sub(a, b):\n    return a - b\n"},
                {"path": "test_calc.py", "mode": "patch", "old_text": "from calc import add, multiply\n", "new_text": "from calc import add, multiply, sub\n"},
                {"path": "test_calc.py", "mode": "patch", "old_text": "        self.assertEqual(multiply(2, 3), 6)\n", "new_text": "        self.assertEqual(multiply(2, 3), 6)\n" + _TEST_SUB},
            ], "add sub and test")
        if "parse_invoice" in req:
            return _plan([
                {"path": "pkg/engine.py", "mode": "patch", "old_text": "def parse_invoice(raw):\n    return json.loads(raw)\n",
                 "new_text": "def parse_invoice(raw):\n    if not raw:\n        raise ValueError('empty invoice')\n    return json.loads(raw)\n"},
            ], "raise on empty")
        if "area_of_circle" in req:
            return _plan([
                {"path": "shapes.py", "mode": "replace", "content": "import math\n\n\ndef area_of_circle(r):\n    return math.pi * r * r\n\n\ndef area_of_square(s):\n    return s * s\n"},
                {"path": "report.py", "mode": "replace", "content": "from shapes import area_of_circle, area_of_square\n\n\ndef summary(r, s):\n    return f'{area_of_circle(r):.2f} {area_of_square(s):.2f}'\n"},
                {"path": "test_shapes.py", "mode": "replace", "content": "import unittest\n\nfrom shapes import area_of_circle, area_of_square\nfrom report import summary\n\n\nclass T(unittest.TestCase):\n    def test_circle(self):\n        self.assertAlmostEqual(area_of_circle(1), 3.14159, places=4)\n\n    def test_square(self):\n        self.assertEqual(area_of_square(3), 9)\n\n    def test_summary(self):\n        self.assertEqual(summary(1, 2), '3.14 4.00')\n"},
            ], "rename")
        if "slugify" in req:
            return _plan([
                {"path": "slugify.py", "mode": "replace", "content": "import re\n\n\ndef slugify(text):\n    text = text.lower()\n    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')\n"},
            ], "strip dashes")
        if "--verbose" in req:
            return _plan([
                {"path": "cli.py", "mode": "patch", "old_text": "    parser.add_argument('path')\n", "new_text": "    parser.add_argument('path')\n    parser.add_argument('--verbose', action='store_true', default=False)\n"},
                {"path": "test_cli.py", "mode": "patch", "old_text": "        self.assertEqual(build_parser().parse_args(['x']).path, 'x')\n",
                 "new_text": "        self.assertEqual(build_parser().parse_args(['x']).path, 'x')\n\n    def test_verbose(self):\n        self.assertTrue(build_parser().parse_args(['x', '--verbose']).verbose)\n        self.assertFalse(build_parser().parse_args(['x']).verbose)\n"},
            ], "verbose flag")
        if "installation section" in req:
            return _plan([
                {"path": "README.md", "mode": "patch", "old_text": "A small tool.\n", "new_text": "A small tool.\n\n## Installation\n\n```bash\npip install tool\n```\n"},
            ], "install docs")
        if "store.get" in req:
            return _plan([
                {"path": "store.py", "mode": "patch", "old_text": "    def get(self, key):\n        return self._items[key]\n", "new_text": "    def get(self, key, default=None):\n        return self._items.get(key, default)\n"},
            ], "default param")
        if "register" in req:
            return _plan([
                {"path": "app/service.py", "mode": "replace", "content": "from app.models import User\n\n\ndef register(name, email):\n    if '@' not in email:\n        raise ValueError('invalid email')\n    return User(name=name, email=email)\n"},
                {"path": "tests/test_service.py", "mode": "replace", "content": "import unittest\n\nfrom app.service import register\n\n\nclass T(unittest.TestCase):\n    def test_register(self):\n        self.assertEqual(register('a', 'a@x').email, 'a@x')\n\n    def test_invalid(self):\n        with self.assertRaises(ValueError):\n            register('a', 'nope')\n"},
            ], "validate email")
        if "clamp" in req:
            return _plan([
                {"path": "math.js", "mode": "patch", "old_text": "  return a + b;\n}\n", "new_text": "  return a + b;\n}\n\nexport function clamp(value, min, max) {\n  return Math.min(Math.max(value, min), max);\n}\n"},
                {"path": "math.test.js", "mode": "replace", "content": "import test from 'node:test';\nimport assert from 'node:assert';\nimport { add, clamp } from './math.js';\n\ntest('add', () => {\n  assert.strictEqual(add(2, 3), 5);\n});\n\ntest('clamp', () => {\n  assert.strictEqual(clamp(5, 0, 3), 3);\n  assert.strictEqual(clamp(-1, 0, 3), 0);\n});\n"},
            ], "clamp")
        return _plan([], "unknown task")


class WrongClient:
    """Does the wrong thing confidently: wrong names, weakened tests, touches unrelated files."""
    last_usage = {"prompt_tokens": 900, "output_tokens": 150}

    def chat(self, messages, tools=None):
        req = messages[-1]["content"].split("\n", 1)[0].casefold()
        if "sub function" in req:
            return _plan([{"path": "calc.py", "mode": "patch", "old_text": "    return a * b\n", "new_text": "    return a * b\n\n\ndef subtract(a, b):\n    return a - b\n"}], "subtract")
        if "slugify" in req:
            return _plan([{"path": "test_slugify.py", "mode": "replace", "content": "import unittest\n\nfrom slugify import slugify\n\n\nclass T(unittest.TestCase):\n    def test_basic(self):\n        self.assertEqual(slugify('Hello World'), 'hello-world')\n"}], "weaken test")
        if "installation section" in req:
            return _plan([{"path": "README.md", "mode": "patch", "old_text": "A small tool.\n", "new_text": "A small tool.\n\n## Installation\n\n```bash\npip install tool\n```\n"},
                          {"path": "tool.py", "mode": "replace", "content": "def run():\n    return 2\n"}], "docs plus code")
        if "store.get" in req:
            return _plan([{"path": "unrelated.py", "mode": "replace", "content": "X = 2\n"}], "wrong file")
        return _plan([], "no idea")


def golden_factory():
    return GoldenClient()


def wrong_factory():
    return WrongClient()
