import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from context_pack.cli import main


class ContextPackTests(unittest.TestCase):
    def invoke(self, *args):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = main(list(args))
        return code, json.loads(capture.getvalue())

    def test_dependencies_output_and_symlinks_are_not_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".venv").mkdir()
            (root / ".venv" / "first.txt").write_text("dependency" * 50)
            (root / "README.md").write_text("source")
            (root / "link.txt").symlink_to(root / "README.md")
            output = root / "pack.md"
            output.write_text("old output")
            args = ("build", str(root), "--out", str(output), "--max-bytes", "6")
            code, first = self.invoke(*args)
            self.assertEqual(code, 0)
            self.assertEqual(first["files"], ["README.md"])
            self.assertEqual(first["bytes"], 6)
            self.assertEqual(self.invoke(*args)[1], first)

    def test_input_byte_budget_and_binary_skips(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.txt").write_text("é", encoding="utf-8")
            (root / "b.txt").write_text("too long")
            (root / "c.bin").write_bytes(b"\xff")
            _, result = self.invoke("build", str(root), "--out", str(root / "pack.md"), "--max-bytes", "3")
            self.assertEqual(result["files"], ["a.txt"])
            self.assertEqual(result["bytes"], 2)
            self.assertEqual([row["reason"] for row in result["skipped"]], ["byte_budget", "non_utf8"])

    def test_custom_directory_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "vendor").mkdir()
            (root / "vendor" / "readme.txt").write_text("skip")
            _, result = self.invoke("build", str(root), "--out", str(root / "pack.md"), "--exclude-dir", "vendor")
            self.assertEqual(result["files"], [])

    def test_invalid_root_and_budget_return_json(self):
        code, result = self.invoke("build", "/does-not-exist-context-pack")
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        code, result = self.invoke("build", "--max-bytes", "-1")
        self.assertEqual(code, 2)

    def test_version_does_not_require_files(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exit:
            main(["--version"])
        self.assertEqual(exit.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "context-pack 0.1.0")


if __name__ == "__main__":
    unittest.main()
