import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from context_pack import __version__
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
            _, result = self.invoke(
                "build",
                str(root),
                "--out",
                str(root / "pack.md"),
                "--max-bytes",
                "3",
            )
            self.assertEqual(result["files"], ["a.txt"])
            self.assertEqual(result["bytes"], 2)
            self.assertEqual(
                [row["reason"] for row in result["skipped"]],
                ["byte_budget", "non_utf8"],
            )

    def test_custom_directory_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "vendor").mkdir()
            (root / "vendor" / "readme.txt").write_text("skip")
            _, result = self.invoke(
                "build",
                str(root),
                "--out",
                str(root / "pack.md"),
                "--exclude-dir",
                "vendor",
            )
            self.assertEqual(result["files"], [])

    def test_manifest_round_trip_is_redacted_and_reproducible(self):
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            for temp in (first_temp, second_temp):
                root = Path(temp)
                (root / "src").mkdir()
                (root / "src" / "main.py").write_text("print('hello')\n")
                (root / "README.md").write_text("# demo\n")
            first_root = Path(first_temp)
            second_root = Path(second_temp)
            first_code, first = self.invoke(
                "build",
                str(first_root),
                "--max-bytes",
                "1000",
                "--out",
                str(first_root / "pack.md"),
                "--manifest",
                str(first_root / "manifest.json"),
            )
            second_code, second = self.invoke(
                "build",
                str(second_root),
                "--max-bytes",
                "1000",
                "--out",
                str(second_root / "pack.md"),
                "--manifest",
                str(second_root / "manifest.json"),
            )
            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
            first_manifest = json.loads((first_root / "manifest.json").read_text())
            self.assertEqual(first_manifest["schema"], "context-pack/manifest/v1")
            self.assertNotIn(str(first_root), json.dumps(first_manifest))
            verify_code, verification = self.invoke(
                "verify",
                str(first_root),
                "--manifest",
                str(first_root / "manifest.json"),
            )
            self.assertEqual(verify_code, 0)
            self.assertTrue(verification["ok"])
            self.assertEqual(verification["pack_state"], "matched")

    def test_changed_source_and_pack_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("before\n")
            self.assertEqual(
                self.invoke(
                    "build",
                    str(root),
                    "--out",
                    str(root / "pack.md"),
                    "--manifest",
                    str(root / "manifest.json"),
                )[0],
                0,
            )
            (root / "README.md").write_text("after\n")
            code, result = self.invoke(
                "verify",
                str(root),
                "--manifest",
                str(root / "manifest.json"),
            )
            self.assertEqual(code, 1)
            self.assertFalse(result["ok"])
            self.assertIn("source_selection_mismatch", result["errors"])

    def test_tampered_pack_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("source\n")
            self.assertEqual(
                self.invoke(
                    "build",
                    str(root),
                    "--out",
                    str(root / "pack.md"),
                    "--manifest",
                    str(root / "manifest.json"),
                )[0],
                0,
            )
            (root / "pack.md").write_text("tampered\n")
            code, result = self.invoke(
                "verify",
                str(root),
                "--manifest",
                str(root / "manifest.json"),
            )
            self.assertEqual(code, 1)
            self.assertFalse(result["ok"])
            self.assertIn("pack_sha256_mismatch", result["errors"])

    def test_manifest_tamper_is_rejected_before_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("source\n")
            self.assertEqual(
                self.invoke(
                    "build",
                    str(root),
                    "--out",
                    str(root / "pack.md"),
                    "--manifest",
                    str(root / "manifest.json"),
                )[0],
                0,
            )
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["selection"]["max_bytes"] = 1
            (root / "manifest.json").write_text(json.dumps(manifest))
            code, result = self.invoke(
                "verify",
                str(root),
                "--manifest",
                str(root / "manifest.json"),
            )
            self.assertEqual(code, 2)
            self.assertFalse(result["ok"])
            self.assertIn("manifest_sha256_mismatch", result["error"])

    def test_diff_reports_file_and_selection_changes(self):
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first_root = Path(first_temp)
            second_root = Path(second_temp)
            (first_root / "README.md").write_text("before\n")
            (second_root / "README.md").write_text("after")
            (second_root / "new.py").write_text("print('new')\n")
            self.assertEqual(
                self.invoke(
                    "build", str(first_root), "--out", str(first_root / "pack.md"),
                    "--manifest", str(first_root / "manifest.json"),
                )[0],
                0,
            )
            self.assertEqual(
                self.invoke(
                    "build", str(second_root), "--max-bytes", "5", "--out", str(second_root / "pack.md"),
                    "--manifest", str(second_root / "manifest.json"),
                )[0],
                0,
            )
            code, result = self.invoke(
                "diff", str(first_root / "manifest.json"), str(second_root / "manifest.json"), "--check",
            )
            self.assertEqual(code, 1)
            self.assertFalse(result["same"])
            self.assertEqual(result["summary"]["changed"], 1)
            self.assertEqual(result["summary"]["added"], 0)
            self.assertGreaterEqual(result["summary"]["digest_changes"], 1)

    def test_diff_ignores_only_artifact_location_changes(self):
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first_root = Path(first_temp)
            second_root = Path(second_temp)
            (first_root / "README.md").write_text("same\n")
            (second_root / "README.md").write_text("same\n")
            self.assertEqual(
                self.invoke(
                    "build", str(first_root), "--out", str(first_root / "one.md"),
                    "--manifest", str(first_root / "one.json"),
                )[0],
                0,
            )
            self.assertEqual(
                self.invoke(
                    "build", str(second_root), "--out", str(second_root / "two.md"),
                    "--manifest", str(second_root / "two.json"),
                )[0],
                0,
            )
            code, result = self.invoke("diff", str(first_root / "one.json"), str(second_root / "two.json"))
            self.assertEqual(code, 0)
            self.assertTrue(result["same"])
            self.assertEqual(result["summary"]["artifact_changes"], 2)

    def test_hard_link_output_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            source.write_text("keep me\n")
            output = root / "pack.md"
            output.hardlink_to(source)
            code, result = self.invoke("build", str(root), "--out", str(output))
            self.assertEqual(code, 2)
            self.assertFalse(result["ok"])
            self.assertIn("hard-link alias", result["error"])
            self.assertEqual(source.read_text(), "keep me\n")

    def test_symlink_output_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            source.write_text("keep me\n")
            output_target = root / "real-pack.md"
            output_target.write_text("sentinel\n")
            output = root / "pack.md"
            output.symlink_to(output_target)
            code, result = self.invoke("build", str(root), "--out", str(output))
            self.assertEqual(code, 2)
            self.assertFalse(result["ok"])
            self.assertIn("symlink", result["error"])
            self.assertEqual(output_target.read_text(), "sentinel\n")

    def test_verify_rejects_symlink_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("source\n")
            self.assertEqual(
                self.invoke(
                    "build",
                    str(root),
                    "--out",
                    str(root / "pack.md"),
                    "--manifest",
                    str(root / "manifest.json"),
                )[0],
                0,
            )
            (root / "pack-copy.md").write_text((root / "pack.md").read_text())
            (root / "pack.md").unlink()
            (root / "pack.md").symlink_to(root / "pack-copy.md")
            code, result = self.invoke(
                "verify",
                str(root),
                "--manifest",
                str(root / "manifest.json"),
            )
            self.assertEqual(code, 1)
            self.assertFalse(result["ok"])
            self.assertIn("pack_alias", result["errors"])

    def test_invalid_root_and_budget_return_json(self):
        code, result = self.invoke("build", "/does-not-exist-context-pack")
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        code, result = self.invoke("build", "--max-bytes", "-1")
        self.assertEqual(code, 2)

    def test_version_matches_package(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exit:
            main(["--version"])
        self.assertEqual(exit.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"context-pack {__version__}")


if __name__ == "__main__":
    unittest.main()
