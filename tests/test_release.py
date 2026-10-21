"""Dependency-light release checks; run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import ast
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_landscape.processing.paper_pdf import acquire_paper_pdf, pdf_cache_path


class PDFCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.local = self.root / "an-existing-paper.pdf"
        # A minimal PDF with a genuine PDF header for the cache validity check.
        self.local.write_bytes(b"%PDF-1.4\n" + b"synthetic PDF for smoke test\n")
        self.paper = SimpleNamespace(paper_id="abc123", title="Demo", pdf_url=None, arxiv_id=None)

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_local_pdf_is_cached_and_reused(self):
        dest, how = acquire_paper_pdf(self.paper, self.root, local_override=self.local)
        self.assertEqual(how, "selected local PDF")
        self.assertEqual(dest, pdf_cache_path(self.root, "abc123"))
        self.assertEqual(dest.read_bytes(), self.local.read_bytes())
        self.local.unlink()
        same, how2 = acquire_paper_pdf(self.paper, self.root)
        self.assertEqual(same, dest)
        self.assertEqual(how2, "cached PDF")

    def test_bad_upload_does_not_overwrite_cached_pdf(self):
        dest, _ = acquire_paper_pdf(self.paper, self.root, local_override=self.local)
        old = dest.read_bytes()
        with self.assertRaises(ValueError):
            acquire_paper_pdf(self.paper, self.root, upload=b"not a pdf")
        self.assertEqual(dest.read_bytes(), old)

    def test_no_pdf_available_has_actionable_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "Choose an existing local PDF"):
            acquire_paper_pdf(self.paper, self.root)


class GraphTest(unittest.TestCase):
    def test_html_escapes_paper_titles(self):
        parsed = ast.parse((ROOT / "app_v01.py").read_text(encoding="utf-8"))
        fn = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "graph_html")
        module = ast.Module(body=[fn], type_ignores=[])
        ns = {"html": __import__("html")}
        exec(compile(module, "<graph-test>", "exec"), ns)
        value = ns["graph_html"]('<script>alert("oops")</script>', 'A & B', "2026", "2025", 2)
        self.assertIn("A &amp; B", value)
        self.assertIn("&lt;script&gt;alert", value)
        self.assertNotIn('<script>alert("oops")</script>', value)
        self.assertIn('pointerdown', value)
        self.assertIn('marker-end="url(#head)"', value)


class ReportTest(unittest.TestCase):
    def test_ordered_pair_and_pdf_content_affect_report_key(self):
        fake_analyzer = types.ModuleType("research_landscape.processing.component_analysis")
        fake_analyzer.VERSION = "coverage-v0.1-5"
        old = sys.modules.get(fake_analyzer.__name__)
        sys.modules[fake_analyzer.__name__] = fake_analyzer
        try:
            from research_landscape.processing.comparison_reports import report_path, save_report, read_report, latest_report
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                a, b = root / "a.pdf", root / "b.pdf"
                a.write_bytes(b"%PDF-1.4\nA")
                b.write_bytes(b"%PDF-1.4\nB")
                forward = report_path(root, "a", "b", a, b)
                reverse = report_path(root, "b", "a", b, a)
                self.assertNotEqual(forward, reverse)
                obj = SimpleNamespace(target=[], source=[], contributions=[], already_covered=[], undecided=[], target_warnings=[], source_warnings=[])
                # save_report serializes dataclasses, so use an actual dataclass.
                from dataclasses import make_dataclass
                cls = make_dataclass("Report", [(k, list) for k in vars(obj)])
                instance = cls(**vars(obj))
                paper_a = SimpleNamespace(paper_id="a", title="Paper A")
                paper_b = SimpleNamespace(paper_id="b", title="Paper B")
                save_report(forward, paper_a, paper_b, instance, a, b)
                self.assertEqual(read_report(forward)["source_title"], "Paper B")
                self.assertEqual(latest_report(root, "a", "b")["target_title"], "Paper A")
                self.assertIsNone(latest_report(root, "b", "a"))
                b.write_bytes(b"%PDF-1.4\nchanged")
                self.assertNotEqual(forward, report_path(root, "a", "b", a, b))
        finally:
            sys.modules.pop("research_landscape.processing.comparison_reports", None)
            if old is None:
                del sys.modules[fake_analyzer.__name__]
            else:
                sys.modules[fake_analyzer.__name__] = old


class DatabaseSearchTest(unittest.TestCase):
    def test_query_is_parameterized(self):
        psycopg = types.ModuleType("psycopg")
        rows = types.ModuleType("psycopg.rows")
        rows.dict_row = object()
        psycopg.rows = rows
        saved = {k: sys.modules.get(k) for k in ("psycopg", "psycopg.rows", "research_landscape.storage.database")}
        sys.modules["psycopg"], sys.modules["psycopg.rows"] = psycopg, rows
        db = types.ModuleType("research_landscape.storage.database")
        commands = []

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql, params): commands.append((sql, params))
            def fetchall(self): return [{"paper_id": "p", "title": "Demo", "year": 2024, "citation_count": 2}]

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def cursor(self, **_): return Cursor()

        db.get_connection = lambda: Connection()
        sys.modules[db.__name__] = db
        try:
            mod = importlib.import_module("research_landscape.storage.paper_library")
            results = mod.search_saved_papers("Robert's 100%_", limit=1000)
            self.assertEqual(len(results), 1)
            sql, params = commands[0]
            self.assertNotIn("Robert's", sql)
            self.assertEqual(params[0], "Robert's 100%_")
            self.assertIn("\\%", params[1])
            self.assertIn("\\_", params[1])
            self.assertEqual(params[-1], 250)
        finally:
            sys.modules.pop("research_landscape.storage.paper_library", None)
            for k, value in saved.items():
                if value is None: sys.modules.pop(k, None)
                else: sys.modules[k] = value

if __name__ == "__main__": unittest.main()
