"""RazaAI: deterministic exploration before planning: symbol index, import graph, test pairing, term search, symbol-level context, completeness check with one retry, session state."""

import json
import tempfile
from pathlib import Path

from app.coding import WorkspaceCoworker
from app.coding.explore import (SessionState, SymbolIndex, import_graph, plan_gaps, request_terms,
                                select_context, term_search, test_pairs)
from app.tools.workspace import WorkspaceManager


def _fixture():
    ws = Path(tempfile.mkdtemp())
    (ws / "pkg").mkdir()
    (ws / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    # A large module: the relevant function is NOT in the file name.
    filler = "".join(f"def filler_{i}(x):\n    return x + {i}\n\n" for i in range(300))
    (ws / "pkg" / "engine.py").write_text(
        "import json\n\n" + filler + "def parse_invoice(raw):\n    return json.loads(raw)\n\n"
        "class Ledger:\n    def total(self):\n        return 0\n", encoding="utf-8")
    (ws / "pkg" / "api.py").write_text("from pkg.engine import parse_invoice\n\ndef handle(body):\n    return parse_invoice(body)\n", encoding="utf-8")
    (ws / "tests").mkdir()
    (ws / "tests" / "test_engine.py").write_text("from pkg.engine import parse_invoice\n\ndef test_parse():\n    assert parse_invoice('{}') == {}\n", encoding="utf-8")
    for i in range(30):
        (ws / f"unrelated_{i}.py").write_text(f"VALUE_{i} = {i}\n", encoding="utf-8")
    (ws / "README.md").write_text("# demo\n", encoding="utf-8")
    return ws


def main():
    print("=" * 78)
    print("RazaAI Step 20.11.0 Exploration Before Planning")
    print("=" * 78)

    ws = _fixture()
    mgr = WorkspaceManager(ws)
    files = [e["path"] for e in mgr.list_files(".", recursive=True, max_entries=500)["entries"] if e["type"] == "file"]

    idx = SymbolIndex(mgr)
    names = [s.name for s in idx.symbols("pkg/engine.py")]
    assert "parse_invoice" in names and "Ledger" in names and "filler_299" in names
    body = idx.body(next(s for s in idx.symbols("pkg/engine.py") if s.name == "parse_invoice"))
    assert body.startswith("def parse_invoice(raw):") and "json.loads" in body
    print("[PASS] Python symbol index locates functions/classes with line ranges and extracts bodies")

    graph = import_graph(idx, files)
    assert "pkg/engine.py" in graph.get("pkg/api.py", set())
    assert "pkg/engine.py" in graph.get("tests/test_engine.py", set())
    pairs = test_pairs(files)
    assert "pkg/engine.py" in pairs.get("tests/test_engine.py", set()) and "tests/test_engine.py" in pairs.get("pkg/engine.py", set())
    print("[PASS] import graph and test<->source pairing are built from the workspace")

    terms = request_terms("make parse_invoice raise ValueError on empty input")
    assert "parse_invoice" in terms and "valueerror" in terms and "empty" in terms and "make" not in terms
    hits = term_search(mgr, ["parse_invoice"])
    assert set(hits) >= {"pkg/engine.py", "pkg/api.py", "tests/test_engine.py"}
    print("[PASS] request terms are extracted and searched across the workspace (rg or Python fallback)")

    sel = select_context(mgr, "make parse_invoice raise ValueError on empty input", files, max_chars=9000, priority_files=("README.md",))
    assert sel.files[0] == "pkg/engine.py", sel.files
    assert "FILE: pkg/engine.py" in sel.rendered and "CLIPPED: yes" in sel.rendered
    assert "def parse_invoice(raw):" in sel.rendered and "filler_150" not in sel.rendered
    assert "pkg/api.py" in sel.files and "tests/test_engine.py" in sel.files
    assert not any(f.startswith("unrelated_") for f in sel.files[:3])
    assert "pkg/engine.py:parse_invoice" in sel.symbols
    assert "tests/test_engine.py" in sel.related_tests
    print("[PASS] a 40-file workspace yields the relevant symbol body, its importer and its test — not keyword-named noise")

    gaps = plan_gaps("add a sub function to calc.py and a unittest for it",
                     {"files": [{"path": "calc.py", "mode": "patch", "old_text": "x", "new_text": "def sub(a,b):\n    return a-b\n"}]},
                     {"calc.py", "test_calc.py"})
    assert len(gaps) == 1 and "touches no test file" in gaps[0] and "test_calc.py" in gaps[0], gaps
    gaps2 = plan_gaps("add a sub function to calc.py and a unittest for it",
                      {"files": [{"path": "calc.py", "mode": "patch", "old_text": "x", "new_text": "def multiply(a,b):\n    return a*b\n"},
                                 {"path": "test_calc.py", "mode": "patch", "old_text": "y", "new_text": "def test_multiply(self): pass\n"}]},
                      {"calc.py", "test_calc.py"})
    assert any("`sub`" in g for g in gaps2), gaps2
    assert plan_gaps("add a sub function and a test", {"files": [{"path": "calc.py", "new_text": "def sub(): pass"}, {"path": "test_calc.py", "new_text": "def test_sub(): pass"}]}, set()) == []
    print("[PASS] completeness check flags missing tests and missing requested names; a complete plan has no gaps")

    ws2 = Path(tempfile.mkdtemp())
    (ws2 / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws2 / "test_calc.py").write_text("import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 1), 2)\n", encoding="utf-8")

    class _ForgetfulThenFixed:
        def __init__(self):
            self.calls = []

        def chat(self, messages, tools=None):
            user = messages[-1]["content"]
            self.calls.append(user)
            if "PREVIOUS PLAN WAS INCOMPLETE" not in user:
                plan = {"files": [{"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n",
                                   "new_text": "    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"}], "summary": "add sub"}
            else:
                assert "touches no test file" in user and "test_calc.py" in user
                plan = {"files": [
                    {"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n",
                     "new_text": "    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "from calc import add\n",
                     "new_text": "from calc import add, sub\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "        self.assertEqual(add(1, 1), 2)\n",
                     "new_text": "        self.assertEqual(add(1, 1), 2)\n\n    def test_sub(self):\n        self.assertEqual(sub(3, 1), 2)\n"},
                ], "summary": "add sub and its test"}
            return {"message": {"content": json.dumps(plan)}}

    client = _ForgetfulThenFixed()
    cw = WorkspaceCoworker(client=client, manager=WorkspaceManager(ws2), require_approval=True)
    proposal = cw.handle("add a sub function to calc.py and a unittest for it")
    assert len(client.calls) == 2, "planner should have been asked once more with the gap"
    assert "### patch `test_calc.py`" in proposal and "test_sub" in proposal
    assert "does NOT fully satisfy" not in proposal
    assert "SESSION STATE" not in client.calls[0]
    report = cw.approve()
    assert "Verification: PASS" in report and "Context given to the planner:" in report
    assert "SESSION STATE" in cw.session.render() and "applied" in cw.session.render()
    print("[PASS] an incomplete plan is sent back once with the concrete gap and the corrected plan is proposed")

    # A patch whose anchor is not in the current file is a gap, fixed before proposing;
    # proposals never show empty diffs; the last error is answerable from Python state.
    ws3 = Path(tempfile.mkdtemp())
    (ws3 / "calc.py").write_text("def add(a,b):\n    return a+b\n\ndef multiply(a,b):\n    return a*b\n", encoding="utf-8")
    (ws3 / "test_calc.py").write_text("import unittest\nfrom calc import add, multiply\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1,1),2)\n", encoding="utf-8")

    class _BadAnchorThenFixed:
        def __init__(self):
            self.calls = []

        def chat(self, messages, tools=None):
            user = messages[-1]["content"]
            self.calls.append(user)
            if "PREVIOUS PLAN WAS INCOMPLETE" not in user:
                plan = {"files": [
                    {"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n", "new_text": "    return a + b\n\ndef sub(a,b):\n    return a-b\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "from calc import add, multiply\n", "new_text": "from calc import add, multiply, sub\n"}],
                    "summary": "add sub"}
            else:
                assert "Patch anchor for calc.py occurs 0 time(s)" in user, user[-600:]
                plan = {"files": [
                    {"path": "calc.py", "mode": "patch", "old_text": "    return a*b\n", "new_text": "    return a*b\n\ndef sub(a,b):\n    return a-b\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "from calc import add, multiply\n", "new_text": "from calc import add, multiply, sub\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "        self.assertEqual(add(1,1),2)\n", "new_text": "        self.assertEqual(add(1,1),2)\n    def test_sub(self):\n        self.assertEqual(sub(3,1),2)\n"}],
                    "summary": "add sub and test"}
            return {"message": {"content": json.dumps(plan)}}

    client3 = _BadAnchorThenFixed()
    cw3 = WorkspaceCoworker(client=client3, manager=WorkspaceManager(ws3), require_approval=True)
    proposal3 = cw3.handle("add a sub function to calc.py and a unittest for it")
    # An 'insert-after' patch with a stale anchor is converted to an append by Python,
    # so no retry is needed; the proposal states it.
    assert len(client3.calls) == 1 and "```diff\n```" not in proposal3 and "+def sub(a,b):" in proposal3, (len(client3.calls), proposal3[:600])
    assert "appended instead" in proposal3
    assert cw3.should_handle("what is the exact error from the patch")
    assert "no recorded error" in cw3.handle("what is the exact error from the patch")
    report3 = cw3.approve()
    assert "Verification: PASS" in report3 and report3.count("- `test_calc.py`") == 1, report3
    assert report3.count("py_compile test_calc.py") == 1, report3

    class _Broken:
        def chat(self, messages, tools=None):
            return {"message": {"content": json.dumps({"files": [{"path": "calc.py", "mode": "patch", "old_text": "NOPE", "new_text": "x"}], "summary": "bad"})}}
    cw4 = WorkspaceCoworker(client=_Broken(), manager=WorkspaceManager(ws3), require_approval=True)
    out4 = cw4.handle("add a div function to calc.py file")
    assert "did not change the workspace" in out4 and "Patch anchor" in out4
    assert "Patch anchor" in cw4.handle("why did it fail?")
    print("[PASS] bad patch anchors are caught before proposing and retried once; the last error is Python-answerable")

    # Syntax errors and silent loss of existing definitions are gaps fixed before proposing.
    ws5 = Path(tempfile.mkdtemp())
    (ws5 / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws5 / "test_calc.py").write_text("import unittest\n\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")
    calls5 = []

    class _SloppyThenFixed:
        def chat(self, messages, tools=None, **kw):
            u = messages[-1]["content"]; calls5.append(u)
            if "PREVIOUS PLAN WAS INCOMPLETE" not in u:
                plan = {"files": [
                    {"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n", "new_text": "    return a + b\n\n\ndef mul(a, b):\nreturn a * b\n"},
                    {"path": "test_calc.py", "mode": "replace", "content": "import unittest\nfrom calc import add, mul\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"}],
                    "summary": "mul"}
            else:
                # The lossy test rewrite is auto-converted to an additive patch; only the real
                # defect (unparsable mul body) is sent back.
                assert "does not parse" in u and "removes existing definitions" not in u, u[-700:]
                plan = {"files": [
                    {"path": "calc.py", "mode": "patch", "old_text": "    return a + b\n", "new_text": "    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"},
                    {"path": "test_calc.py", "mode": "patch", "old_text": "        self.assertEqual(add(2, 3), 5)\n", "new_text": "        self.assertEqual(add(2, 3), 5)\n\n    def test_mul(self):\n        from calc import mul\n        self.assertEqual(mul(2, 3), 6)\n"}],
                    "summary": "mul with patch"}
            return {"message": {"content": json.dumps(plan)}}
    cw5 = WorkspaceCoworker(client=_SloppyThenFixed(), manager=WorkspaceManager(ws5), require_approval=True)
    p5 = cw5.handle("add a function named mul(a, b) that returns a * b to calc.py and a unittest for it")
    assert len(calls5) == 2 and "### patch `test_calc.py`" in p5 and "does NOT fully" not in p5
    assert "Verification: PASS" in cw5.approve()
    assert "test_add" in (ws5 / "test_calc.py").read_text(encoding="utf-8")
    # A rename request may legitimately drop the old name
    cw6 = WorkspaceCoworker(client=_SloppyThenFixed(), manager=WorkspaceManager(ws5), require_approval=True)
    cw6._rewrite_requested = True
    assert cw6._symbol_loss_gaps({"files": [{"path": "calc.py", "mode": "replace", "content": "def plus(a, b):\n    return a + b\n"}]}) == []
    # The repair pass applies the same parse check before writing.
    err = cw5._would_not_parse("calc.py", {"mode": "patch", "old_text": "    return a + b\n", "new_text": "    return a + b\n\n\ndef bad(:\n"})
    assert err and "line" in err
    assert cw5._would_not_parse("calc.py", {"mode": "patch", "old_text": "    return a + b\n", "new_text": "    return a + b\n\n\ndef good():\n    return 1\n"}) is None
    assert "_would_not_parse(path, item)" in Path("app/coding/coworker.py").read_text(encoding="utf-8").split("def _repair(")[1]
    print("[PASS] unparsable patches and silent removal of existing tests are caught and retried before any proposal; repair cannot write unparsable code")

    # Python hands the planner unique patch anchors; append mode needs no anchor.
    import re as _re
    from app.coding.explore import patch_anchors
    ws7 = Path(tempfile.mkdtemp())
    (ws7 / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n", encoding="utf-8")
    (ws7 / "test_calc.py").write_text("import unittest\n\nfrom calc import add, mul\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n\n\nif __name__ == '__main__':\n    unittest.main()\n", encoding="utf-8")
    hints = patch_anchors((ws7 / "test_calc.py").read_text(encoding="utf-8"), "test_calc.py")
    assert "add a method to class T" in hints and "mode=append" in hints
    seen7 = {}

    class _UsesAnchors:
        def chat(self, messages, tools=None, **kw):
            u = messages[-1]["content"]; seen7["u"] = u
            anchor = json.loads(_re.search(r'add a method to class T: patch old_text=("(?:[^"\\]|\\.)*")', u).group(1))
            return {"message": {"content": json.dumps({"files": [
                {"path": "calc.py", "mode": "append", "content": "def neg(a):\n    return -a\n"},
                {"path": "test_calc.py", "mode": "patch", "old_text": anchor,
                 "new_text": anchor + "\n    def test_neg(self):\n        from calc import neg\n        self.assertEqual(neg(3), -3)\n"}], "summary": "neg"})}}
    cw7 = WorkspaceCoworker(client=_UsesAnchors(), manager=WorkspaceManager(ws7), require_approval=True)
    p7 = cw7.handle("add a function named neg(a) that returns -a to calc.py and a unittest for it")
    assert "PATCH ANCHORS" in seen7["u"] and "### append `calc.py`" in p7 and "does NOT fully" not in p7
    assert "Verification: PASS" in cw7.approve()
    src7 = (ws7 / "calc.py").read_text(encoding="utf-8"); tst7 = (ws7 / "test_calc.py").read_text(encoding="utf-8")
    assert "def mul" in src7 and "def neg" in src7 and "test_add" in tst7 and "test_neg" in tst7
    print("[PASS] planner receives unique patch anchors; append mode adds to existing files without an anchor")

    # Anchors are provided for clipped files too; planner traces feed the seed exporter.
    big = "".join(f"def mul{i}(a, b):\n    return a * b\n\n\n" for i in range(120)) + "def last(a):\n    return a\n"
    ws8 = Path(tempfile.mkdtemp()); (ws8 / "calc.py").write_text(big, encoding="utf-8")
    sel8 = select_context(WorkspaceManager(ws8), "add a function named neg(a) that returns -a to calc.py", ["calc.py"], max_chars=9000)
    assert "CLIPPED: yes" in sel8.rendered and "PATCH ANCHORS" in sel8.rendered and "NEVER replace" in sel8.rendered
    import os as _os, subprocess as _sp, sys as _sys
    trace_root = Path(tempfile.mkdtemp())
    env = dict(_os.environ, RAZAAI_CODER_TRACE="1", RAZAAI_CODER_TRACE_DIR=str(trace_root / "coder_traces"), PYTHONPATH=str(Path.cwd()))
    ws9 = Path(tempfile.mkdtemp()); (ws9 / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws9 / "test_calc.py").write_text("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1,1),2)\n", encoding="utf-8")
    code = (
        "import json\nfrom app.coding import WorkspaceCoworker\nfrom app.tools.workspace import WorkspaceManager\n"
        "class Bad:\n    def chat(self, messages, tools=None, **k):\n        return {'message': {'content': json.dumps({'files': ["
        "{'path': 'calc.py', 'mode': 'append', 'content': 'def neg(a):\\n    return a\\n'},"
        "{'path': 'test_calc.py', 'mode': 'patch', 'old_text': '    def test_add(self):\\n        self.assertEqual(add(1,1),2)\\n',"
        " 'new_text': '    def test_add(self):\\n        self.assertEqual(add(1,1),2)\\n\\n    def test_neg(self):\\n        from calc import neg\\n        self.assertEqual(neg(1), -1)\\n'}],"
        "'summary': 'neg'})}}\n"
        f"WorkspaceCoworker(client=Bad(), manager=WorkspaceManager({str(ws9)!r})).handle('add a function named neg(a) that returns -a to calc.py and a unittest for it')\n"
    )
    _sp.run([_sys.executable, "-c", code], env=env, check=True, capture_output=True)
    out = _sp.run([_sys.executable, "-m", "scripts.export_coder_seed"], env=env, capture_output=True, text=True, cwd=trace_root)
    pending = trace_root / "training" / "coder_v2_seed" / "pending.jsonl"
    assert pending.is_file() and "1 new record" in out.stdout, out.stdout + out.stderr
    rec = json.loads(pending.read_text(encoding="utf-8").splitlines()[0])
    assert rec["passed"] is False and rec["corrected_plan"] is None and "PATCH ANCHORS" in rec["user"] and any("FAIL" in f for f in rec["failure"])
    print("[PASS] clipped files carry anchors; failed plans are traced and exported as seed records awaiting a corrected plan")

    # A new test that uses a name the module never imports is a gap with the import line as anchor.
    ws10 = Path(tempfile.mkdtemp())
    (ws10 / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef neg1(a):\n    return -a\n", encoding="utf-8")
    (ws10 / "test_calc.py").write_text("import unittest\n\nfrom calc import add, neg1\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n    def test_neg1(self):\n        self.assertEqual(neg1(3), -3)\n", encoding="utf-8")
    calls10 = []

    class _ForgetsImport:
        def chat(self, messages, tools=None, **kw):
            u = messages[-1]["content"]; calls10.append(u)
            anchor = "    def test_neg1(self):\n        self.assertEqual(neg1(3), -3)\n"
            if "PREVIOUS PLAN WAS INCOMPLETE" not in u:
                plan = {"files": [{"path": "calc.py", "mode": "append", "content": "def neg2(a):\n    return -a\n"},
                                  {"path": "test_calc.py", "mode": "patch", "old_text": anchor, "new_text": anchor + "\n    def test_neg2(self):\n        self.assertEqual(neg2(5), -5)\n"}], "summary": "neg2"}
            else:
                assert "uses `neg2`, which is not imported" in u and 'old_text="from calc import add, neg1\\n"' in u and "defined in calc.py" in u, u[-700:]
                plan = {"files": [{"path": "calc.py", "mode": "append", "content": "def neg2(a):\n    return -a\n"},
                                  {"path": "test_calc.py", "mode": "patch", "old_text": "from calc import add, neg1\n", "new_text": "from calc import add, neg1, neg2\n"},
                                  {"path": "test_calc.py", "mode": "patch", "old_text": anchor, "new_text": anchor + "\n    def test_neg2(self):\n        self.assertEqual(neg2(5), -5)\n"}], "summary": "neg2 with import"}
            return {"message": {"content": json.dumps(plan)}}
    cw10 = WorkspaceCoworker(client=_ForgetsImport(), manager=WorkspaceManager(ws10), require_approval=True)
    p10 = cw10.handle("add a function named neg2(a) that returns -a to calc.py and a unittest for it")
    assert len(calls10) == 1 and "does NOT fully" not in p10, (len(calls10), p10[-400:])
    assert "added `neg2` to `from calc import add, neg1`" in p10
    assert "Verification: PASS" in cw10.approve()
    assert "neg2" in (ws10 / "test_calc.py").read_text(encoding="utf-8").splitlines()[2]
    print("[PASS] a forgotten import is completed by Python (no extra planner call) and stated in the proposal")

    # Stale 'insert-after' anchors become appends; lossy rewrites keep existing methods.
    ws11 = Path(tempfile.mkdtemp())
    (ws11 / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef neg1(a):\n    return -a\n", encoding="utf-8")
    (ws11 / "test_calc.py").write_text("import unittest\n\nfrom calc import add, neg1\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n    def test_neg1(self):\n        self.assertEqual(neg1(3), -3)\n", encoding="utf-8")

    class _StaleAndLossy:
        def chat(self, messages, tools=None, **kw):
            return {"message": {"content": json.dumps({"files": [
                {"path": "calc.py", "mode": "patch", "old_text": "def neg0(a):\n    return -a\n", "new_text": "def neg0(a):\n    return -a\n\n\ndef neg2(a):\n    return -a\n"},
                {"path": "test_calc.py", "mode": "replace", "content": "import unittest\n\nfrom calc import add, neg1, neg2\n\n\nclass T(unittest.TestCase):\n    def test_neg2(self):\n        self.assertEqual(neg2(5), -5)\n"}],
                "summary": "neg2"})}}
    cw11 = WorkspaceCoworker(client=_StaleAndLossy(), manager=WorkspaceManager(ws11), require_approval=True)
    p11 = cw11.handle("add a function named neg2(a) that returns -a to calc.py and a unittest for it")
    assert "does NOT fully" not in p11 and "appended instead" in p11 and "would have dropped methods ['test_add', 'test_neg1']" in p11
    assert "Verification: PASS" in cw11.approve()
    tc11 = (ws11 / "test_calc.py").read_text(encoding="utf-8")
    assert "test_add" in tc11 and "test_neg1" in tc11 and "test_neg2" in tc11 and "def neg1" in (ws11 / "calc.py").read_text(encoding="utf-8")
    print("[PASS] stale anchors become appends and lossy rewrites are converted to additive patches, stated in the proposal")

    # "add mul3" done as "replace mul2 with mul3" (the 7B's dominant habit) becomes additive.
    ws12 = Path(tempfile.mkdtemp())
    (ws12 / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul2(a, b):\n    return a * b\n", encoding="utf-8")
    (ws12 / "test_calc.py").write_text("import unittest\n\nfrom calc import add, mul2\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n    def test_mul2(self):\n        self.assertEqual(mul2(2, 3), 6)\n", encoding="utf-8")

    class _Substitutes:
        def chat(self, messages, tools=None, **kw):
            return {"message": {"content": json.dumps({"files": [
                {"path": "calc.py", "mode": "patch", "old_text": "def mul2(a, b):\n    return a * b\n", "new_text": "def mul3(a, b):\n    return a * b\n"},
                {"path": "test_calc.py", "mode": "patch", "old_text": "    def test_mul2(self):\n        self.assertEqual(mul2(2, 3), 6)\n", "new_text": "    def test_mul3(self):\n        self.assertEqual(mul3(2, 3), 6)\n"}],
                "summary": "mul3"})}}
    cw12 = WorkspaceCoworker(client=_Substitutes(), manager=WorkspaceManager(ws12), require_approval=True)
    p12 = cw12.handle("add a function named mul3(a, b) that returns a * b to calc.py and a unittest for it")
    assert "does NOT fully" not in p12 and "would have replaced ['mul2'] with ['mul3']" in p12 and "added `mul3`" in p12
    assert "Verification: PASS" in cw12.approve()
    src12, tc12 = (ws12 / "calc.py").read_text(encoding="utf-8"), (ws12 / "test_calc.py").read_text(encoding="utf-8")
    assert "def mul2" in src12 and "def mul3" in src12 and "test_mul2" in tc12 and "test_mul3" in tc12
    print("[PASS] substitution patches (replace the previous function with the new one) are made additive")

    state = SessionState()
    for i in range(20):
        state.record("applied", f"change {i}", touched=[f"f{i}.py"])
    rendered = state.render()
    assert len(rendered) <= SessionState.MAX_CHARS and "change 19" in rendered and "change 0" not in rendered
    print("[PASS] session state is a bounded rolling summary injected into later plans")

    print("=" * 78)
    print("STEP 20.11.0 EXPLORATION BEFORE PLANNING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
